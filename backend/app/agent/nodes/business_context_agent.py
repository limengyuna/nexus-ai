"""
Business Context Agent 节点

职责：
- 专门读取当前登录用户在 NexusAI 系统内的受控业务上下文。
- 执行只读业务上下文工具。
"""
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.agent.llm import get_llm_fast
from app.agent.state import AgentState, StepOutput, append_trace
from app.agent.stream_queue import get_queue, with_stream_interceptor
from app.agent.tools.business_context import (
    AgentRuntimeContext,
    list_business_context_tools,
    get_business_context_tool
)
from app.agent.observation import build_business_context_observation


BUSINESS_CONTEXT_SYSTEM_PROMPT = """你是 NexusAI 的业务上下文助手。

职责：
- 只能读取当前用户在 NexusAI 系统内的受控业务上下文。
- 可用工具会以 function calling 形式提供。
- 你可以查询账号概览、知识库/文档状态、当前会话、MCP 配置等。

安全规则：
- 必须基于工具返回结果回答，不要编造。
- 不要声称可以访问任意数据库或执行 SQL。
- 不要请求或猜测 user_id、session_id，这些由系统运行时注入。
- 查询知识库文档时，必须使用系统运行时注入的 kb_id，或上一步工具结果中已经返回的知识库 id 作为 kb_ids；没有可靠 id 时先调用 get_knowledge_base_overview。
- 如果 Supervisor 指令明确指定了工具名和参数，必须按这些参数调用工具，不要只用文字复述计划。
- 如果工具返回错误或无数据，如实说明。"""


def _select_fallback_tool(text: str) -> str:
    """根据关键词做简单的规则 fallback"""
    if any(k in text for k in ["账号", "用户", "工作区", "我有多少", "统计", "概览"]):
        return "get_user_workspace_summary"
    if any(k in text for k in ["知识库", "文档", "上传", "处理状态", "失败"]):
        return "get_knowledge_base_overview"
    if any(k in text for k in ["MCP", "工具配置", "外部工具", "服务"]):
        return "get_mcp_server_overview"
    return "get_current_session_summary"


def _parse_tool_arguments(raw_args: Any) -> Dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if not raw_args or not isinstance(raw_args, str):
        return {}
    try:
        parsed = json.loads(raw_args)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_int_list(text: str, key: str) -> List[int]:
    match = re.search(rf"[\"']?\b{re.escape(key)}\b[\"']?\s*(?:=|:|为|是)\s*(\[[^\]]*\]|\d+)", text)
    if not match:
        return []
    return [int(n) for n in re.findall(r"\d+", match.group(1))]


def _forced_tool_call_from_instruction(instruction: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """当 Supervisor 已经明确给出工具名和参数时，直接执行，避免模型二次决策丢参。"""
    if not instruction:
        return None

    if "get_knowledge_base_documents" in instruction:
        kb_ids = _extract_int_list(instruction, "kb_ids") or _extract_int_list(instruction, "kb_id")
        if not kb_ids:
            kb_ids = [int(n) for n in re.findall(r"知识库\s*ID\s*(?:=|:|为|是)?\s*(\d+)", instruction, flags=re.IGNORECASE)]
        if kb_ids:
            return "get_knowledge_base_documents", {"kb_ids": kb_ids}
        return None

    for tool_name in (
        "get_knowledge_base_overview",
        "get_user_workspace_summary",
        "get_current_session_summary",
        "get_mcp_server_overview",
    ):
        if tool_name in instruction:
            return tool_name, {}
    return None


def _format_direct_tool_answer(tool_name: str, arguments: Dict[str, Any], result: Any) -> str:
    if isinstance(result, dict) and result.get("error"):
        return f"查询失败：{result['error']}"

    if tool_name == "get_knowledge_base_documents" and isinstance(result, dict):
        items = result.get("items", [])
        if not items:
            return f"已查询知识库 {arguments.get('kb_ids', [])}，没有找到文档。"

        lines = [f"已查询知识库 {arguments.get('kb_ids', [])} 的文档，共 {result.get('total', len(items))} 个："]
        for item in items:
            lines.append(
                f"- KB {item.get('kb_id')} / 文档 {item.get('id')}: "
                f"{item.get('file_name')}（状态: {item.get('status')}, chunks: {item.get('chunk_count')}）"
            )
        return "\n".join(lines)

    if tool_name == "get_knowledge_base_overview" and isinstance(result, dict):
        items = result.get("items", [])
        if not items:
            return "当前用户没有知识库。"
        lines = [f"当前共有 {result.get('total', len(items))} 个知识库："]
        for item in items:
            lines.append(
                f"- {item.get('name')}（ID: {item.get('id')}, 文档: {item.get('document_count')}, "
                f"已完成: {item.get('completed_documents')}）"
            )
        return "\n".join(lines)

    return "已完成业务上下文查询。"


@with_stream_interceptor
def business_context_agent_node(state: AgentState) -> Dict[str, Any]:
    started_at = time.time()
    user_input = state.get("user_input", "")
    instruction = state.get("supervisor_instruction") or user_input
    session_id = state.get("session_id")
    user_id = state.get("user_id")

    token_queue = get_queue(session_id)
    response_mode = state.get("response_mode", "direct")
    
    if token_queue:
        token_queue.put(("meta", {
            "intent": "business_context",
            "route_reason": "读取用户业务上下文",
            "task_plan": state.get("task_plan", [])
        }))

    llm = get_llm_fast()
    
    runtime_context = AgentRuntimeContext(
        user_id=user_id,
        session_id=session_id,
        kb_id=state.get("kb_id"),
    )

    tools = list_business_context_tools()
    openai_tools = [t.to_openai_schema() for t in tools]

    messages = state.get("messages", []).copy()
    if not messages:
        messages = [{"role": "user", "content": user_input}]
        
    messages.insert(0, {"role": "system", "content": BUSINESS_CONTEXT_SYSTEM_PROMPT})
    if instruction and instruction != user_input:
         messages.append({"role": "user", "content": f"Supervisor 指令：{instruction}"})

    context_records = []
    node_tokens = 0
    final_answer = ""

    forced_call = _forced_tool_call_from_instruction(instruction)
    if forced_call:
        tool_name, arguments = forced_call
        tool = get_business_context_tool(tool_name)
        tool_started = time.time()
        if not tool:
            tool_result = {"error": f"未知工具: {tool_name}"}
        else:
            try:
                tool_result = tool.run_with_context(arguments, runtime_context)
            except Exception as e:
                logger.exception(f"[Business Context Agent] 工具执行异常: {e}")
                tool_result = {"error": str(e)}
        elapsed_ms = int((time.time() - tool_started) * 1000)
        context_records.append({
            "name": tool_name,
            "arguments": arguments,
            "result": tool_result,
            "elapsed_ms": elapsed_ms,
            "error": tool_result.get("error") if isinstance(tool_result, dict) else None,
            "trust_level": "execution_verified" if not (isinstance(tool_result, dict) and tool_result.get("error")) else "failed"
        })
        final_answer = _format_direct_tool_answer(tool_name, arguments, tool_result)
    else:
        for _ in range(3):
            resp = llm.complete_with_tools(messages=messages, tools=openai_tools, temperature=0.1)
            usage = resp.get("usage", {})
            node_tokens += usage.get("total_tokens", 0)

            content = resp.get("content")
            tool_calls = resp.get("tool_calls", [])

            if not tool_calls and content:
                final_answer = content
                break

            # 处理 function calling
            if tool_calls:
                tc = tool_calls[0]
                tool_name = tc.get("name")
                # 保持原始 args 用于构造安全的 role="assistant" 消息
                raw_args = tc.get("arguments", "{}")
                arguments = _parse_tool_arguments(raw_args)
                tc_id = tc.get("id", "call_1")
                
                messages.append({
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": [{"id": tc_id, "type": "function", "function": {"name": tool_name, "arguments": raw_args}}],
                })
                
                tool = get_business_context_tool(tool_name)
                tool_started = time.time()
                if not tool:
                    tool_result = {"error": f"未知工具: {tool_name}"}
                else:
                    try:
                        tool_result = tool.run_with_context(arguments, runtime_context)
                    except Exception as e:
                        logger.exception(f"[Business Context Agent] 工具执行异常: {e}")
                        tool_result = {"error": str(e)}
                        
                elapsed_ms = int((time.time() - tool_started) * 1000)
                
                context_records.append({
                    "name": tool_name,
                    "arguments": arguments,
                    "result": tool_result,
                    "elapsed_ms": elapsed_ms,
                    "error": tool_result.get("error") if isinstance(tool_result, dict) else None,
                    "trust_level": "execution_verified" if not (isinstance(tool_result, dict) and tool_result.get("error")) else "failed"
                })
                
                from app.agent.tool_result import compact_for_llm
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": json.dumps(compact_for_llm(tool_result), ensure_ascii=False)})
            else:
                final_answer = "未能获取有效的业务上下文结果。"
                break

    if not final_answer and not context_records:
        # Fallback
        tool_name = _select_fallback_tool(user_input)
        tool = get_business_context_tool(tool_name)
        tool_started = time.time()
        try:
            tool_result = tool.run_with_context({}, runtime_context)
        except Exception as e:
            tool_result = {"error": str(e)}
        elapsed_ms = int((time.time() - tool_started) * 1000)
        context_records.append({
            "name": tool_name,
            "arguments": {},
            "result": tool_result,
            "elapsed_ms": elapsed_ms,
            "error": tool_result.get("error") if isinstance(tool_result, dict) else None,
            "trust_level": "execution_verified" if not (isinstance(tool_result, dict) and tool_result.get("error")) else "failed"
        })
        from app.agent.tool_result import compact_for_llm
        # 用普通 user 消息把工具结果交给模型总结，避免 OpenAI 对孤立 tool message 报错
        compacted = json.dumps(compact_for_llm(tool_result), ensure_ascii=False)
        messages.append({"role": "user", "content": f"系统自动获取了上下文数据：\n{compacted}\n请根据该数据回答用户的原始问题。"})
        
        # one more LLM call to summarize
        resp = llm.complete_with_tools(messages=messages, tools=openai_tools, temperature=0.1)
        usage = resp.get("usage", {})
        node_tokens += usage.get("total_tokens", 0)
        content = resp.get("content")
        final_answer = content if content else "已查阅业务上下文，请见详细数据。"

    if token_queue and final_answer and response_mode != "deferred":
        token_queue.put(("chunk", final_answer))

    obs = build_business_context_observation(context_records, final_answer)
    
    # 补充 step 信息
    task_plan = state.get("task_plan", [])
    current_step = 0
    for s in task_plan:
        if s.get("status") == "in_progress":
            current_step = s.get("step", 0)
            break
            
    risk_flags = []
    failures = []
    for record in context_records:
        if record.get("error"):
            failures.append(record["error"])
            risk_flags.append("context_retrieval_failed")
            
    step_output = StepOutput(
        step=current_step or 0,
        agent="business_context_agent",
        instruction=instruction,
        status="failed" if failures else "completed",
        answer=final_answer,
        summary=final_answer[:200],
        model_generated=[final_answer] if final_answer else [],
        failures=failures,
        risk_flags=risk_flags
    )

    return {
        "final_answer": final_answer,
        "retrieved_business_context": context_records,
        "latest_observation": obs,
        "agent_observations": [obs],
        "step_outputs": [step_output],
        "total_tokens": state.get("total_tokens", 0) + node_tokens,
        "execution_trace": append_trace(
            state,
            "business_context_agent",
            started_at,
            input_summary={"user_input": user_input[:80]},
            output_summary={"context_count": len(context_records), "tokens": node_tokens},
        )
    }
