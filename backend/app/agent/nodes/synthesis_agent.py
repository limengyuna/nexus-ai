"""
Synthesis Agent 节点

职责：
作为多步计划的最后一环，综合各子 Agent 的执行结果（StepOutputs），生成最终的安全总结回答。

核心架构：降维幻觉的双阶段生成
1. 阶段一：LLM 从各步骤摘要中提取结构化的 SynthesisClaim。
2. 阶段二：Python 代码进行决定论式的安全性与事实校验。
3. 阶段三：基于验证后的 Claim 组装 Markdown 并推送给前端。
"""
import json
import time
from typing import Any, Dict, List

from loguru import logger

from app.agent.llm import get_llm_fast
from app.agent.state import AgentState, StepOutput, SynthesisClaim, append_trace
from app.agent.stream_queue import get_queue


_SYNTHESIS_EXTRACT_PROMPT = """你是一个严谨的总结生成器。
当前系统刚刚完成了用户分配的多步复杂任务。请基于下面提供的各步骤执行结果，总结出最终回答。

规则：
1. 提取所有关键信息点，并将其结构化为多个事实声明（Claims）。
2. 每条 Claim 必须附带其信息的来源步骤（source_step_ids）。
3. 切勿自行编造未在执行结果中出现过的信息。
4. 严格输出 JSON 格式，不要添加其他文字。

执行结果（StepOutputs）：
{step_outputs}

输出格式示例：
{{
    "claims": [
        {{
            "text": "用户的知识库总共有 3 个",
            "source_step_ids": [1]
        }}
    ],
    "overall_summary": "给用户的总结性陈述（不包含具体的风险警告，单纯的总结语）"
}}
"""

def synthesis_agent_node(state: AgentState) -> Dict[str, Any]:
    started_at = time.time()
    user_input = state.get("user_input", "")
    session_id = state.get("session_id")
    token_queue = get_queue(session_id)
    step_outputs = state.get("step_outputs", [])
    
    llm = get_llm_fast()
    node_tokens = 0
    
    # 构造摘要供 LLM 提取
    outputs_summary = []
    for out in step_outputs:
        outputs_summary.append({
            "step": out.get('step'),
            "agent": out.get('agent'),
            "status": out.get('status'),
            "summary": out.get('summary'),
            "answer": str(out.get('answer', ''))[:1500],
            "risk_flags": out.get('risk_flags', []),
            "external_unverified": out.get('external_unverified', [])
        })
        
    messages = [
        {"role": "system", "content": _SYNTHESIS_EXTRACT_PROMPT.format(step_outputs=json.dumps(outputs_summary, ensure_ascii=False, indent=2))},
        {"role": "user", "content": f"用户原始提问：{user_input}\n请开始提取总结 claims。"}
    ]
    
    try:
        raw_output, usage = llm.complete_counted(
            messages=messages,
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        node_tokens += usage.get("total_tokens", 0)
        parsed = json.loads(raw_output)
        claims_raw = parsed.get("claims", [])
        overall_summary = parsed.get("overall_summary", "总结如下：")
    except Exception as e:
        logger.exception("[Synthesis Agent] 提取 Claim 失败: {}", e)
        # 降级：直接拼接各个步骤
        claims_raw = []
        overall_summary = "执行完毕。以下为各步骤摘要："
        for out in step_outputs:
            claims_raw.append({
                "text": out.get('summary'),
                "source_step_ids": [out.get('step')]
            })
            
    # 阶段二：决定论式校验 (Deterministic Verification)
    verified_claims: List[SynthesisClaim] = []
    for c in claims_raw:
        source_ids = c.get("source_step_ids", [])
        if not isinstance(source_ids, list):
            source_ids = [source_ids] if isinstance(source_ids, int) else []
            
        trust_level = "execution_verified"
        risk_flags = []
        evidence_refs = []
        
        # 校验来源
        has_failed_source = False
        has_unverified = False
        has_inferred = False
        valid_source_found = False
        for sid in source_ids:
            # 找到对应的 step
            step_obj = next((s for s in step_outputs if s.get("step") == sid), None)
            if step_obj:
                valid_source_found = True
                if step_obj.get("status") == "failed":
                    has_failed_source = True
                if step_obj.get("external_unverified"):
                    has_unverified = True
                if step_obj.get("inferred"):
                    has_inferred = True
                if step_obj.get("risk_flags"):
                    risk_flags.extend(step_obj.get("risk_flags"))
                if step_obj.get("evidence_refs"):
                    evidence_refs.extend(step_obj.get("evidence_refs"))
                    
        if not valid_source_found:
            trust_level = "inferred"
            risk_flags.append("no_valid_source")
        elif has_failed_source:
            trust_level = "failed"
            risk_flags.append("source_failed")
        elif has_unverified:
            trust_level = "external_unverified"
        elif has_inferred:
            trust_level = "inferred"
            
        verified_claims.append({
            "text": str(c.get("text", "")),
            "source_step_ids": source_ids,
            "evidence_refs": evidence_refs,
            "trust_level": trust_level,
            "risk_flags": list(set(risk_flags))
        })
        
    # 阶段三：渲染 Markdown
    lines = []
    if overall_summary:
        lines.append(f"💡 {overall_summary}\n")
        
    for i, claim in enumerate(verified_claims, 1):
        prefix = "✅" if claim["trust_level"] == "execution_verified" else "⚠️"
        lines.append(f"{i}. {prefix} {claim['text']}")
        if claim["risk_flags"]:
            lines.append(f"   > 存在风险: {', '.join(claim['risk_flags'])}")
            
    final_answer = "\n".join(lines)
    
    # 向前端推送
    if token_queue:
        # 发送 chunk
        token_queue.put(("chunk", final_answer))
        # 因为这是最后一站，我们发送 done
        token_queue.put(("done", None))
        
    return {
        "final_answer": final_answer,
        "synthesis_completed": True,
        "total_tokens": state.get("total_tokens", 0) + node_tokens,
        "execution_trace": append_trace(
            state,
            "synthesis_agent",
            started_at,
            input_summary={"steps_count": len(step_outputs)},
            output_summary={"claims_count": len(verified_claims), "tokens": node_tokens}
        )
    }
