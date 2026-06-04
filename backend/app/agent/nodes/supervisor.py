"""
Supervisor Agent 节点 — 动态 Task Plan 方案

职责：多 Agent 协作的调度中心（LLM 驱动）
- 首次调用：分析用户请求，生成 task_plan（任务拆解列表）
- 后续调用：子 Agent 完成后，LLM 判断是按 plan 继续还是调整
- 闲聊/简单问答直接自己回答（plan 为空）
- 输出 next_agent 字段供图条件边路由

设计原则：
- Supervisor 只做"规划+指挥"，不执行具体任务
- task_plan 是可观测的执行计划，前端可展示
- 最多循环 MAX_ITERATIONS 次，防止无限循环
"""
import json
import re
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from app.agent.llm import get_llm_fast
from app.agent.skills import skill_registry
from app.agent.state import AgentState, append_trace


# Supervisor 可分发的目标
NEXT_RAG = "rag_agent"
NEXT_TOOL = "tool_agent"
NEXT_BUSINESS_CONTEXT = "business_context_agent"
NEXT_FINISH = "FINISH"

# Supervisor 最大循环次数（防止无限循环）
MAX_ITERATIONS = 5


# ---------- Prompt 模板 ----------

def _build_planning_prompt(has_kb: bool, mcp_info: List[Dict[str, str]]) -> str:
    """构建任务规划 prompt（首次调用时使用）"""
    capabilities = ", ".join(f"{s['name']}({s['description']})" for s in skill_registry.to_choices_for_router())

    kb_section = "- **rag_agent**：从用户关联的知识库中检索文档内容并生成回答。" if has_kb else "- **rag_agent**：不可用（用户未关联知识库）。"

    # 动态构建 MCP 工具描述
    if mcp_info:
        mcp_lines = "；外部工具(MCP)：" + "、".join(
            f"{m['name']}({m['description']})" if m['description'] else m['name']
            for m in mcp_info
        )
    else:
        mcp_lines = ""

    return f"""你是 NexusAI 的 Supervisor（调度者）。分析用户请求，制定执行计划。

## 可用子 Agent
{kb_section}
- **tool_agent**：执行工具和技能（{capabilities}）{mcp_lines}。
- **business_context_agent**：读取当前用户在 NexusAI 系统内的受控业务上下文，例如账号信息、工作区概览、知识库/文档状态、当前会话、MCP 配置等。只读，不执行任意 SQL。
- **FINISH**：你自己直接回答，不需要子 Agent。

## 任务

分析用户请求，输出 JSON 执行计划。

### 规则
- 简单请求（闲聊、问候、常识）：plan 为空数组，直接用 answer 回答
- business_context_agent 用于查询当前用户在系统中的个人业务数据，包括：账号与工作区概览、知识库和文档的数量与处理状态、MCP 工具配置、当前会话信息。仅当用户询问的是自己在系统中的实时状态（如"我有几个知识库""我的文档处理完了吗""我配了哪些MCP"）时才使用。
- tool_agent 用于所有用户要求「调用工具」「执行操作」「删除」「更新」「导出」等动作型请求，以及通用 Skill（计算、天气、搜索）和外部 MCP 工具。即使涉及系统内对象，只要意图是执行动作而非查询个人状态，就路由给 tool_agent。
- rag_agent 用于所有需要从知识库检索规章制度、操作手册、技术规范等静态知识的问题。即使提到系统概念（如"差旅制度""SLA规定"），只要答案来源于文档而非用户个人实时数据，就路由给 rag_agent。
- 不要直接回答“无法获取”，除非 business_context_agent 返回错误或无数据。
- 单步请求（只需一个 Agent）：plan 只有 1 个 step
- 复合请求（如"查知识库再写文件"）：plan 有多个 step，按顺序执行
- 每个 step 的 agent 只能是 rag_agent、tool_agent 或 business_context_agent
- instruction 要具体明确，让子 Agent 知道该做什么

### needs_previous_output 字段
- **true**：本步的执行依赖前一步或前一轮对话的具体输出内容（即：如果不提供那段内容，本步就无法正确完成）
- **false**：本步可独立执行，所需信息已在 instruction 中完整给出

### 输出格式（严格 JSON）
{{"plan": [{{"step": 1, "agent": "rag_agent|tool_agent|business_context_agent", "instruction": "具体指令", "needs_previous_output": false}}], "answer": "plan为空时的直接回答，有plan时留空"}}

只输出 JSON，不要任何其他文字。"""


def _build_step_check_prompt() -> str:
    """构建步骤检查 prompt（子 Agent 完成后使用）"""
    return """你是 NexusAI 的 Supervisor。上一步任务已完成，请决定下一步行动。

## 规则
- 如果当前 plan 中还有待执行步骤，继续执行下一步
- 如果执行结果不理想，可以调整剩余 plan（修改或追加步骤）
- 如果所有步骤都已完成，选择 FINISH

## 输出格式（严格 JSON）
{"action": "next|adjust|finish", "reason": "简短理由", "instruction": "给下一个Agent的指令（finish时留空）", "adjusted_plan": [{"step": N, "agent": "...", "instruction": "...", "needs_previous_output": false}]}

- action=next：按原计划执行下一步
- action=adjust：调整剩余计划（用 adjusted_plan 替换剩余步骤）
- action=finish：所有任务完成
- adjusted_plan 的每个 step 必须带 needs_previous_output 字段：true 表示需要引用前一步的输出内容

只输出 JSON。"""


# ---------- 工具函数 ----------

# step_context 截断长度（防止 context window 过载）
_STEP_CONTEXT_MAX_LEN = 6000


def _get_last_assistant_msg(context_messages: List[Dict]) -> str:
    """从对话历史中倒序查找最近一条 assistant 消息的 content。
    用于跨轮场景下"上一步内容"的回溯（如新一轮用户说"把上一步写入文件"）。
    """
    for msg in reversed(context_messages):
        if msg.get("role") == "assistant":
            return msg.get("content", "") or ""
    return ""


def _get_mcp_info(user_id: Optional[int]) -> List[Dict[str, str]]:
    """
    获取用户配置的 MCP 服务器列表（名称+描述）。
    返回空列表表示无可用 MCP。
    """
    if user_id is None:
        return []
    try:
        from app.core.database import SessionLocal
        from app.models.mcp_server import MCPServerConfig
        db = SessionLocal()
        try:
            configs = (
                db.query(MCPServerConfig)
                .filter(MCPServerConfig.created_by == user_id, MCPServerConfig.is_active.is_(True))
                .all()
            )
            return [
                {"name": c.name, "description": c.description or ""}
                for c in configs
            ]
        finally:
            db.close()
    except Exception:
        return []


def _extract_json(text: str) -> Optional[dict]:
    """鲁棒提取 JSON：正则匹配 {...}，兼容 markdown 包裹"""
    clean = text.strip()
    # 移除 markdown 代码块
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    # 正则提取（支持嵌套的 JSON，贪婪匹配最外层）
    # 先尝试整体解析
    try:
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        pass
    # 尝试正则提取
    match = re.search(r'\{.*\}', clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    Supervisor 决策节点（动态 Task Plan）。

    流程：
    1. 首次调用（iterations==0）：LLM 生成 task_plan
       - plan 为空 → 闲聊，自己回答
       - plan 非空 → 执行第一步
    2. 后续调用（iterations>0）：子 Agent 完成后
       - LLM 判断：继续下一步 / 调整计划 / 结束
    """
    started_at = time.time()
    user_input = state.get("user_input", "")
    kb_id = state.get("kb_id")
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    from app.agent.stream_queue import get_queue
    from app.agent.cancel_registry import is_cancelled
    token_queue = get_queue(session_id)
    iterations = state.get("agent_iterations", 0)
    final_answer = state.get("final_answer", "")
    task_plan = state.get("task_plan", [])
    context_messages = state.get("context_messages", [])

    # ---------- 协作式取消：用户主动中断（"取消即终止"方案）----------
    # 设计演进说明：
    # 早期版本用 LangGraph interrupt() 暂停 graph + Command(resume) 智能续跑（"Cursor 风格"），
    # 但实践中发现这套机制存在心智模型不一致——用户的"继续" ≠ 系统的"复用半成品状态"。
    # 改造为业界主流做法：用户取消 → 直接终止当前轮次，下次发消息走新一轮 graph 执行。
    #
    # 跨轮记忆机制：当前 task_plan 的 step 状态（completed / cancelled）通过
    # ChatMessage.task_plan_meta 字段持久化（chat_service 写入），下一轮 supervisor
    # 规划阶段（_planning_phase）会读取它，让 LLM 知道哪些 step 已完成、跳过它们重做未完成的。
    if is_cancelled(session_id):
        logger.info(
            "[Supervisor] 检测到用户取消信号，终止当前轮次 (session_id={}, task_plan_steps={})",
            session_id, len(task_plan)
        )
        # 把当前 in_progress / pending 的 step 标为 cancelled，让下一轮 LLM 看到"哪些被中断了"
        for step in task_plan:
            if step.get("status") in ("in_progress", "pending"):
                step["status"] = "cancelled"
        # 直接走 _finish_done 终止本轮（cancelled 标志让兜底逻辑写"已停止"，不去拼 tool_calls 结果）
        return _finish_done(
            state, task_plan, token_queue, iterations, started_at, 0,
            reason="用户主动中断", cancelled=True,
        )

    has_kb = kb_id is not None
    mcp_info = _get_mcp_info(user_id)

    llm = get_llm_fast()
    node_tokens = 0

    # ---------- 防止无限循环 ----------
    if iterations >= MAX_ITERATIONS:
        logger.warning("[Supervisor] 达到最大迭代次数 {}，强制结束", MAX_ITERATIONS)
        if token_queue:
            if not final_answer:
                token_queue.put(("meta", {"intent": "supervisor", "route_reason": "超时强制结束"}))
                token_queue.put(("chunk", "抱歉，处理过程超时，请简化您的请求后重试。"))
            token_queue.put(("done", None))
        return {
            "next_agent": NEXT_FINISH,
            "final_answer": final_answer or "处理超时",
            "agent_iterations": iterations,
            "execution_trace": append_trace(
                state, "supervisor", started_at,
                output_summary={"next": NEXT_FINISH, "reason": "max_iterations"},
            ),
        }

    # ==========================================================
    # 首次调用：规划阶段 — 生成 task_plan
    # ==========================================================
    if iterations == 0:
        return _planning_phase(
            state, llm, has_kb, mcp_info, context_messages,
            user_input, token_queue, started_at,
        )

    # ==========================================================
    # 后续调用：执行检查阶段 — 判断下一步
    # ==========================================================
    return _execution_phase(
        state, llm, task_plan, context_messages,
        user_input, final_answer, token_queue, iterations, started_at,
    )


# ---------- 规划阶段 ----------

def _planning_phase(
    state: AgentState, llm, has_kb: bool, mcp_info: List[Dict[str, str]],
    context_messages: List[Dict], user_input: str,
    token_queue, started_at: float,
) -> Dict[str, Any]:
    """首次调用：LLM 分析请求，生成 task_plan"""
    node_tokens = 0
    system_prompt = _build_planning_prompt(has_kb, mcp_info)

    # ---------- 跨轮记忆：上一轮被中断的 task_plan ----------
    # state.last_task_plan_meta 由 chat_service 在调用 graph 前从上一轮 ChatMessage.task_plan_meta 注入。
    # 如果上一轮被用户中断（meta.interrupted=True），把 task_plan 状态拼到 prompt，
    # 让 LLM 看到 "哪些 step 已完成（completed）/ 哪些被中断（cancelled）"，
    # 自然在新一轮的 plan 里跳过已完成的、重做被中断的。
    last_meta = state.get("last_task_plan_meta") or {}
    if last_meta.get("interrupted") and last_meta.get("task_plan"):
        prev_plan = last_meta["task_plan"]
        plan_summary_lines = []
        for st in prev_plan:
            status = st.get("status", "")
            mark = "✓ 已完成" if status == "completed" else ("✗ 用户中断" if status == "cancelled" else f"({status})")
            plan_summary_lines.append(f"  - step {st.get('step')}: {st.get('instruction', '')[:80]} {mark}")
        plan_summary = "\n".join(plan_summary_lines)
        system_prompt += (
            "\n\n📌 上一轮任务执行情况（用户中断了）：\n"
            f"{plan_summary}\n\n"
            "请基于上述情况生成新一轮 plan：\n"
            "  - **已完成（✓）的 step 不要再做** —— 用户和系统都已认可这些步骤已经成功，重做没意义；\n"
            "  - **被中断（✗）的 step 如果用户当前消息是「继续/接着做」等续跑意图，必须重新规划这些步骤**；\n"
            "  - 如果用户当前消息是新需求（换话题、新指令），按新需求重新规划，不必延续上一轮的 plan。\n"
        )
        logger.info("[Supervisor._planning_phase] 注入上一轮被中断的 task_plan 上下文（{} 个 step）", len(prev_plan))

    messages = [
        {"role": "system", "content": system_prompt},
        *context_messages,
    ]

    # 调用 LLM 生成计划
    try:
        resp_text, usage = llm.complete_counted(messages=messages, temperature=0.1, max_tokens=300)
        node_tokens = usage.get("total_tokens", 0)
    except Exception as e:
        logger.exception("[Supervisor] 规划 LLM 失败: {}", e)
        # 降级：闲聊回答
        return _finish_with_chitchat(state, llm, context_messages, token_queue, started_at, node_tokens, f"规划失败: {e}")

    logger.debug("[Supervisor] 规划 LLM 输出: {}", resp_text[:300])

    # 解析 JSON
    parsed = _extract_json(resp_text)
    if parsed is None:
        logger.warning("[Supervisor] 规划 JSON 解析失败，原文: {}", resp_text[:200])
        # 降级：把 LLM 输出当作直接回答
        return _finish_with_chitchat(state, llm, context_messages, token_queue, started_at, node_tokens, "规划JSON解析失败")

    # 提取 plan 和 answer
    plan = parsed.get("plan", [])
    direct_answer = parsed.get("answer", "")

    # 校验 plan 中的 agent 合法性
    valid_plan = []
    for step in plan:
        agent = step.get("agent", "")
        if agent not in {NEXT_RAG, NEXT_TOOL, NEXT_BUSINESS_CONTEXT}:
            continue
        # 如果没有 KB 但分配了 rag_agent，跳过
        if agent == NEXT_RAG and not has_kb:
            continue
        valid_plan.append({
            "step": len(valid_plan) + 1,
            "agent": agent,
            "instruction": step.get("instruction", user_input),
            "needs_previous_output": bool(step.get("needs_previous_output", False)),
            "status": "pending",
        })

    # 编程式打包 step_contexts：
    # - 第一步若 needs_previous_output=true：取对话历史最近一条 assistant 消息（跨轮引用）
    # - 后续步骤的 context 在 _dispatch_step 时用 state.final_answer 动态填充
    step_contexts: Dict[int, str] = {}
    if valid_plan and valid_plan[0].get("needs_previous_output"):
        last_assistant = _get_last_assistant_msg(context_messages)
        if last_assistant:
            step_contexts[valid_plan[0]["step"]] = last_assistant[:_STEP_CONTEXT_MAX_LEN]
            logger.info("[Supervisor] step {} 跨轮引用上一轮回答 ({} 字)",
                        valid_plan[0]["step"], len(last_assistant))

    # plan 为空 → 闲聊，Supervisor 自己回答
    if not valid_plan:
        answer = direct_answer or ""
        if not answer:
            return _finish_with_chitchat(state, llm, context_messages, token_queue, started_at, node_tokens, "简单请求直接回答")

        # 有 direct_answer，直接推送
        if token_queue:
            token_queue.put(("meta", {"intent": "chitchat", "route_reason": "Supervisor直接回答", "task_plan": []}))
            token_queue.put(("chunk", answer))
            token_queue.put(("done", None))

        return {
            "next_agent": NEXT_FINISH,
            "intent": "chitchat",
            "route_reason": "Supervisor直接回答",
            "final_answer": answer,
            "task_plan": [],
            "agent_iterations": 1,
            "total_tokens": state.get("total_tokens", 0) + node_tokens,
            "execution_trace": append_trace(
                state, "supervisor", started_at,
                input_summary={"user_input": user_input[:80]},
                output_summary={"next": NEXT_FINISH, "plan_size": 0, "tokens": node_tokens},
            ),
        }

    # 有 plan → 标记第一步为 in_progress，开始执行
    valid_plan[0]["status"] = "in_progress"
    first_step = valid_plan[0]
    next_agent = first_step["agent"]
    instruction = first_step["instruction"]

    # 映射 intent
    if next_agent == NEXT_RAG:
        intent = "rag"
    elif next_agent == NEXT_TOOL:
        intent = "tool"
    elif next_agent == NEXT_BUSINESS_CONTEXT:
        intent = "business_context"
    else:
        intent = "chitchat"
    reason = f"执行计划 step 1/{len(valid_plan)}: {instruction[:30]}"

    logger.info("[Supervisor] 生成计划 ({} 步) → 执行 step 1: {} | {}", len(valid_plan), next_agent, instruction[:50])

    # 推送 meta（含 plan 信息）
    if token_queue:
        token_queue.put(("meta", {
            "intent": intent,
            "route_reason": reason,
            "task_plan": valid_plan,
        }))

    return {
        "next_agent": next_agent,
        "intent": intent,
        "route_reason": reason,
        "supervisor_instruction": instruction,
        "task_plan": valid_plan,
        "step_contexts": step_contexts,
        "agent_iterations": 1,
        "total_tokens": state.get("total_tokens", 0) + node_tokens,
        "execution_trace": append_trace(
            state, "supervisor", started_at,
            input_summary={"user_input": user_input[:80]},
            output_summary={"next": next_agent, "plan": valid_plan, "tokens": node_tokens},
        ),
    }


# ---------- 执行检查阶段 ----------

def _execution_phase(
    state: AgentState, llm, task_plan: List[Dict],
    context_messages: List[Dict], user_input: str, final_answer: str,
    token_queue, iterations: int, started_at: float,
) -> Dict[str, Any]:
    """子 Agent 完成后：LLM 判断下一步"""
    node_tokens = 0

    # 标记当前执行中的步骤为 completed
    current_step_idx = None
    for i, step in enumerate(task_plan):
        if step.get("status") == "in_progress":
            task_plan[i]["status"] = "completed"
            current_step_idx = i
            break

    # 查找下一个 pending 步骤
    next_pending_idx = None
    for i, step in enumerate(task_plan):
        if step.get("status") == "pending":
            next_pending_idx = i
            break

    # 如果已经没有 pending 步骤，直接看 LLM 是否需要调整
    # 构建 step-check messages
    system_prompt = _build_step_check_prompt()
    plan_summary = json.dumps(task_plan, ensure_ascii=False, indent=2)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"用户原始请求：{user_input}\n\n"
            f"当前执行计划：\n{plan_summary}\n\n"
            f"最新执行结果（摘要）：\n{final_answer[:1500]}\n\n"
            "请决定下一步。严格输出 JSON。"
        )},
    ]

    try:
        resp_text, usage = llm.complete_counted(messages=messages, temperature=0.1, max_tokens=300)
        node_tokens = usage.get("total_tokens", 0)
    except Exception as e:
        logger.exception("[Supervisor] step-check LLM 失败: {}", e)
        # 降级：如果有 pending 步骤继续，否则结束
        if next_pending_idx is not None:
            return _dispatch_step(state, task_plan, next_pending_idx, token_queue, iterations, started_at, node_tokens)
        return _finish_done(state, task_plan, token_queue, iterations, started_at, node_tokens, "LLM失败，plan已完成")

    logger.debug("[Supervisor] step-check LLM 输出: {}", resp_text[:300])

    # 解析 JSON
    parsed = _extract_json(resp_text)
    if parsed is None:
        logger.warning("[Supervisor] step-check JSON 解析失败: {}", resp_text[:200])
        # 降级：有 pending 就继续，没有就结束
        if next_pending_idx is not None:
            return _dispatch_step(state, task_plan, next_pending_idx, token_queue, iterations, started_at, node_tokens)
        return _finish_done(state, task_plan, token_queue, iterations, started_at, node_tokens, "JSON解析失败，plan已完成")

    action = parsed.get("action", "finish")
    reason = parsed.get("reason", "")
    instruction = parsed.get("instruction", "")

    logger.info("[Supervisor] step-check → action={} | reason={} | iteration={}", action, reason, iterations)

    if action == "finish":
        return _finish_done(state, task_plan, token_queue, iterations, started_at, node_tokens, reason)

    if action == "adjust":
        # 调整计划：用 adjusted_plan 替换剩余的 pending 步骤
        adjusted = parsed.get("adjusted_plan", [])
        # 移除旧的 pending 步骤
        task_plan = [s for s in task_plan if s.get("status") != "pending"]
        # 追加新步骤
        for new_step in adjusted:
            agent = new_step.get("agent", "")
            if agent in {NEXT_RAG, NEXT_TOOL, NEXT_BUSINESS_CONTEXT}:
                task_plan.append({
                    "step": len(task_plan) + 1,
                    "agent": agent,
                    "instruction": new_step.get("instruction", ""),
                    "needs_previous_output": bool(new_step.get("needs_previous_output", False)),
                    "status": "pending",
                })
        logger.info("[Supervisor] 调整计划，新增 {} 步", len(adjusted))
        # 找到第一个 pending 并执行
        for i, step in enumerate(task_plan):
            if step.get("status") == "pending":
                return _dispatch_step(state, task_plan, i, token_queue, iterations, started_at, node_tokens)
        # 调整后也没有 pending 了
        return _finish_done(state, task_plan, token_queue, iterations, started_at, node_tokens, "调整后无待执行步骤")

    # action == "next"：继续执行下一步
    if next_pending_idx is not None:
        # 如果 LLM 提供了新的 instruction，覆盖原 plan 中的
        if instruction:
            task_plan[next_pending_idx]["instruction"] = instruction
        return _dispatch_step(state, task_plan, next_pending_idx, token_queue, iterations, started_at, node_tokens)

    # 没有 pending 了，结束
    return _finish_done(state, task_plan, token_queue, iterations, started_at, node_tokens, reason or "所有步骤已完成")


# ---------- 辅助：分发步骤 ----------

def _dispatch_step(
    state: AgentState, task_plan: List[Dict], step_idx: int,
    token_queue, iterations: int, started_at: float, node_tokens: int
) -> Dict[str, Any]:
    """分发指定步骤给子 Agent"""
    task_plan[step_idx]["status"] = "in_progress"
    step = task_plan[step_idx]
    next_agent = step["agent"]
    instruction = step["instruction"]
    if next_agent == NEXT_RAG:
        intent = "rag"
    elif next_agent == NEXT_TOOL:
        intent = "tool"
    elif next_agent == NEXT_BUSINESS_CONTEXT:
        intent = "business_context"
    else:
        intent = "chitchat"
    reason = f"执行 step {step['step']}/{len(task_plan)}: {instruction[:30]}"

    # 动态填充 step_context：
    # - 非首步且 needs_previous_output=true → 用 state.final_answer（前一步执行完写入的）
    # - 若 step_contexts 中已有内容（例如 planning 阶段就打包好的跨轮引用），保留不覆盖
    step_contexts = dict(state.get("step_contexts", {}))
    if step.get("needs_previous_output") and step["step"] not in step_contexts:
        previous_output = state.get("final_answer", "") or ""
        if previous_output:
            step_contexts[step["step"]] = previous_output[:_STEP_CONTEXT_MAX_LEN]
            logger.info("[Supervisor] step {} 引用上一步输出 ({} 字)",
                        step["step"], len(previous_output))

    logger.info("[Supervisor] 分发 step {} → {} | {}", step["step"], next_agent, instruction[:50])

    # 实时推送 meta 消息给前端，同步任务执行状态（例如：第一步变完成，第二步变执行中）
    if token_queue:
        token_queue.put(("meta", {
            "intent": intent,
            "route_reason": reason,
            "task_plan": task_plan,
        }))

    return {
        "next_agent": next_agent,
        "intent": intent,
        "route_reason": reason,
        "supervisor_instruction": instruction,
        "task_plan": task_plan,
        "step_contexts": step_contexts,
        "agent_iterations": iterations + 1,
        "total_tokens": state.get("total_tokens", 0) + node_tokens,
        "execution_trace": append_trace(
            state, "supervisor", started_at,
            input_summary={"step": step["step"], "iteration": iterations},
            output_summary={"next": next_agent, "instruction": instruction[:60], "tokens": node_tokens},
        ),
    }


# ---------- 辅助：结束 ----------

def _finish_done(
    state: AgentState, task_plan: List[Dict],
    token_queue, iterations: int, started_at: float, node_tokens: int, reason: str,
    cancelled: bool = False,
) -> Dict[str, Any]:
    """所有步骤完成（或被用户取消），发送 done 信号
    cancelled=True 时：写"已停止"占位文案，让用户下次发"继续"重做未完成的 step
    cancelled=False 时：正常 finish，按 skill > tool 优先级兜底 final_answer"""
    # 仅在正常 finish 场景把 pending/in_progress 标 completed
    # cancelled 场景调用方已经把 in_progress/pending 标为 cancelled，这里不动
    if not cancelled:
        for step in task_plan:
            if step.get("status") in ("pending", "in_progress"):
                step["status"] = "completed"

    # 确定最终 intent（取最后一个 completed 步骤的 agent 类型）
    last_agent = ""
    for step in reversed(task_plan):
        if step.get("status") == "completed":
            last_agent = step["agent"]
            break
    if cancelled:
        intent = "cancelled"
    elif last_agent == NEXT_RAG:
        intent = "rag"
    elif last_agent == NEXT_TOOL:
        intent = "tool"
    elif last_agent == NEXT_BUSINESS_CONTEXT:
        intent = "business_context"
    else:
        intent = "chitchat"

    # ---------- final_answer 处理 ----------
    final_answer = state.get("final_answer", "") or ""

    if cancelled:
        # 用户主动取消：写一段简洁的"已停止"占位，提示用户可以发"继续"重做未完成的 step
        # 不去拼 tool_calls 结果（避免出现"Successfully wrote..."这种状态字符串作为答案）
        completed_count = sum(1 for s in task_plan if s.get("status") == "completed")
        cancelled_count = sum(1 for s in task_plan if s.get("status") == "cancelled")
        if completed_count > 0 and cancelled_count > 0:
            cancel_msg = f"⏸️ 已停止。\n\n已完成 {completed_count} 个步骤，剩余 {cancelled_count} 个步骤被中断。\n\n如需继续，请发送「继续」或重新描述需求。"
        elif cancelled_count > 0:
            cancel_msg = "⏸️ 已停止。\n\n如需继续，请发送「继续」或重新描述需求。"
        else:
            cancel_msg = "⏸️ 已停止。"
        # 用户取消场景：固定写占位文案，覆盖任何已有的部分输出
        final_answer = cancel_msg
    else:
        # 正常 finish 但 final_answer 为空：按 skill > tool 优先级兜底
        # （场景：tool_agent 跑完工具但 LLM 总结失败、超时强制结束等）
        if not final_answer:
            tool_calls = state.get("tool_calls", []) or []
            for tc in reversed(tool_calls):
                if tc.get("kind") == "skill":
                    result = tc.get("result")
                    if isinstance(result, str) and result.strip():
                        final_answer = result
                        logger.info(
                            "[Supervisor._finish_done] final_answer 为空，使用最近 skill '{}' 的 result 作为兜底 ({} 字)",
                            tc.get("name"), len(final_answer)
                        )
                        break
            if not final_answer:
                for tc in reversed(tool_calls):
                    result = tc.get("result")
                    if isinstance(result, str) and result.strip() and "error" not in (result[:50].lower()):
                        final_answer = result
                        logger.info(
                            "[Supervisor._finish_done] 使用最近 tool '{}' 的 result 作为兜底 ({} 字)",
                            tc.get("name"), len(final_answer)
                        )
                        break

    # 推送 chunks（如果 final_answer 是兜底/取消占位拿到的，需要主动推给前端）
    if token_queue:
        # 仅当 state 中原本没有 final_answer（即兜底/取消场景）时才推 chunk
        # 正常路径下 tool_agent 已经推过 chunk 了，避免重复推
        if final_answer and not (state.get("final_answer", "") or ""):
            token_queue.put(("chunk", final_answer))
        elif cancelled:
            # 取消场景必须强制推送占位文案，覆盖前端 chat 框（即使 state 中有部分 final_answer）
            # 前端 assistantRef.content 之前可能累积了部分 LLM 输出，append cancel_msg 让用户看到状态
            token_queue.put(("chunk", "\n\n" + final_answer if state.get("final_answer") else final_answer))
        # 推送最终 task_plan 状态（含 cancelled 标记），让前端渲染中断信息
        token_queue.put(("meta", {
            "intent": intent,
            "route_reason": reason or ("用户中断" if cancelled else "所有步骤已完成"),
            "task_plan": task_plan,
        }))
        token_queue.put(("done", None))

    return {
        "next_agent": NEXT_FINISH,
        "intent": intent,
        "route_reason": reason,
        "task_plan": task_plan,
        "final_answer": final_answer,
        "agent_iterations": iterations + 1,
        "total_tokens": state.get("total_tokens", 0) + node_tokens,
        "execution_trace": append_trace(
            state, "supervisor", started_at,
            input_summary={"iteration": iterations, "cancelled": cancelled},
            output_summary={"next": NEXT_FINISH, "reason": reason, "tokens": node_tokens},
        ),
    }


# ---------- 辅助：闲聊回答 ----------

def _finish_with_chitchat(
    state: AgentState, llm, context_messages: List[Dict],
    token_queue, started_at: float, node_tokens: int, reason: str
) -> Dict[str, Any]:
    """Supervisor 直接回答闲聊/简单请求"""
    chitchat_messages = [
        {"role": "system", "content": "你是 NexusAI 智能助手。简洁友好地回答用户问题，使用中文。"},
        *context_messages,
    ]
    answer = ""
    try:
        if token_queue:
            token_queue.put(("meta", {"intent": "chitchat", "route_reason": reason, "task_plan": []}))
            chunks = []
            for tok in llm.complete_stream(messages=chitchat_messages, temperature=0.6, max_tokens=800):
                chunks.append(tok)
                token_queue.put(("chunk", tok))
            answer = "".join(chunks)
        else:
            answer, chat_usage = llm.complete_counted(messages=chitchat_messages, temperature=0.6, max_tokens=800)
            node_tokens += chat_usage.get("total_tokens", 0)
    except Exception as e:
        logger.exception("[Supervisor] 闲聊回答失败: {}", e)
        answer = "抱歉，我暂时无法处理这个请求，请稍后再试。"
        if token_queue:
            token_queue.put(("chunk", answer))

    if token_queue:
        token_queue.put(("done", None))

    return {
        "next_agent": NEXT_FINISH,
        "intent": "chitchat",
        "route_reason": reason,
        "final_answer": answer,
        "task_plan": [],
        "agent_iterations": 1,
        "total_tokens": state.get("total_tokens", 0) + node_tokens,
        "execution_trace": append_trace(
            state, "supervisor", started_at,
            output_summary={"next": NEXT_FINISH, "reason": reason, "tokens": node_tokens},
        ),
    }
