"""
Tool Agent 节点

职责：
- 优先匹配 Skill（基于关键词），命中则直接执行 Skill（一次性产出回答）
- 未命中 Skill，则用 LLM Function Calling 自动决定调用哪个/哪些 Tool
- 支持调用 MCP 外部工具（从用户配置的 MCP Server 动态拉取）
- 调用结果反馈给 LLM，生成自然语言回答

体现：Skill > Tool > MCP Tool 的分层抽象。
"""
import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.agent.llm import get_llm
from app.agent.skills import skill_registry
from app.agent.state import AgentState, ToolCallRecord, append_trace
from app.agent.tools import get_tool, tool_registry

_TOOL_AGENT_SYSTEM_PROMPT = """你是 NexusAI 的工具执行助手。

根据用户问题，决定调用哪些工具来获取信息，然后用自然语言回答用户。

可用工具会以 function calling 的形式提供。

约束：
1. 必须基于工具返回的结果回答，不要编造
2. 如果一个工具返回了错误，再尝试用其他工具或直接告知用户
3. 回答简洁清晰，使用中文
4. 如果不需要工具就能回答，直接回答"""


def _try_skill(state: AgentState, started_at: float) -> Dict[str, Any] | None:
    """优先尝试匹配并执行 Skill。命中则返回完整 update dict，否则返回 None。"""
    user_input = state.get("user_input", "")
    skill = skill_registry.match_by_keywords(user_input)
    if skill is None:
        return None

    logger.info("[Tool Agent] 命中技能: {}", skill.name)
    try:
        result = skill.execute(user_input)
    except Exception as e:
        logger.exception("[Tool Agent] Skill 执行失败: {}", e)
        return None  # 降级到工具直调路径

    tool_calls: List[ToolCallRecord] = [
        ToolCallRecord(
            name=tc["name"],
            kind=tc.get("kind", "tool"),
            arguments=tc.get("arguments", {}),
            result=tc.get("result"),
        )
        for tc in result.get("tool_calls", [])
    ]

    return {
        "skill_used": skill.name,
        "tool_calls": tool_calls,
        "final_answer": result.get("answer", ""),
        "execution_trace": append_trace(
            state, "tool_agent", started_at,
            input_summary={"user_input": user_input[:60], "match": "skill", "skill": skill.name},
            output_summary={
                "tool_call_count": len(tool_calls),
                "answer_preview": result.get("answer", "")[:80],
            },
        ),
    }


def _load_mcp_tools(user_id: Optional[int]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    加载当前用户配置的 MCP 外部工具，转换为 OpenAI Function Calling schema。

    :return: (openai_tool_schemas, mcp_tool_map)
        - openai_tool_schemas: OpenAI 格式的工具列表
        - mcp_tool_map: {tool_name: config_id} 用于调用时定位 MCP Server
    """
    if user_id is None:
        return [], {}

    from app.core.database import SessionLocal
    from app.models.mcp_server import MCPServerConfig

    db = SessionLocal()
    schemas: List[Dict[str, Any]] = []
    tool_map: Dict[str, int] = {}  # tool_name → config_id

    try:
        configs = (
            db.query(MCPServerConfig)
            .filter(
                MCPServerConfig.created_by == user_id,
                MCPServerConfig.is_active.is_(True),
            )
            .all()
        )
        if not configs:
            return [], {}

        from app.mcp.client import list_external_tools

        for config in configs:
            try:
                tools = asyncio.run(list_external_tools(config.id))
                for t in tools:
                    # 加前缀避免与内部工具重名
                    prefixed_name = f"mcp_{config.id}_{t['name']}"
                    schemas.append({
                        "type": "function",
                        "function": {
                            "name": prefixed_name,
                            "description": f"[MCP: {config.name}] {t.get('description', '')}",
                            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                        },
                    })
                    tool_map[prefixed_name] = config.id
                logger.info("[Tool Agent] MCP '{}' 加载 {} 个外部工具", config.name, len(tools))
            except Exception as e:
                logger.warning("[Tool Agent] MCP '{}' 工具加载失败: {}", config.name, e)
    finally:
        db.close()

    return schemas, tool_map


def _invoke_mcp_tool(config_id: int, original_name: str, arguments: Dict[str, Any]) -> Any:
    """调用 MCP 外部工具（同步包装异步调用）"""
    from app.mcp.client import invoke_external_tool
    try:
        return asyncio.run(invoke_external_tool(config_id, original_name, arguments))
    except Exception as e:
        logger.exception("[Tool Agent] MCP 工具 {} 调用失败", original_name)
        return {"error": str(e)}


def _function_calling_loop(state: AgentState, started_at: float) -> Dict[str, Any]:
    """LLM Function Calling 主循环（最多 3 轮，避免死循环）"""
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")
    llm = get_llm()

    # 合并内部工具 + MCP 外部工具
    openai_tools = tool_registry.to_openai_tools()
    mcp_schemas, mcp_tool_map = _load_mcp_tools(user_id)
    if mcp_schemas:
        openai_tools = openai_tools + mcp_schemas
        logger.info("[Tool Agent] 工具总计: {} 内部 + {} MCP 外部",
                     len(openai_tools) - len(mcp_schemas), len(mcp_schemas))

    if not openai_tools:
        # 没有可用工具，直接让 LLM 回答
        answer = llm.complete(
            messages=[
                {"role": "system", "content": _TOOL_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            temperature=0.3,
        )
        return {
            "final_answer": answer,
            "tool_calls": [],
            "execution_trace": append_trace(
                state, "tool_agent", started_at,
                input_summary={"user_input": user_input[:60], "match": "no_tools"},
                output_summary={"answer_preview": answer[:80]},
            ),
        }

    # 多轮 function calling
    messages = [
        {"role": "system", "content": _TOOL_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]
    tool_call_records: List[ToolCallRecord] = []
    final_answer = ""

    MAX_TURNS = 3
    for turn in range(MAX_TURNS):
        resp = llm.complete_with_tools(messages=messages, tools=openai_tools)
        finish_reason = resp["finish_reason"]
        content = resp["content"]
        tool_calls = resp["tool_calls"]

        # LLM 决定直接回答（不调工具）
        if not tool_calls or finish_reason == "stop":
            final_answer = content
            break

        # 把 assistant 的 tool_calls 消息追加到 messages
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls
            ],
        })

        # 依次执行每个工具调用
        for tc in tool_calls:
            tool_name = tc["name"]
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}

            # 区分内部工具和 MCP 外部工具
            if tool_name in mcp_tool_map:
                # MCP 外部工具：从带前缀的名字还原原始工具名
                config_id = mcp_tool_map[tool_name]
                # prefixed_name = "mcp_{config_id}_{original_name}"
                original_name = tool_name.split("_", 2)[2] if tool_name.count("_") >= 2 else tool_name
                tool_result = _invoke_mcp_tool(config_id, original_name, args)
                tool_kind = "mcp_tool"
            else:
                tool_kind = "tool"
                tool = get_tool(tool_name)
                if tool is None:
                    tool_result = {"error": f"未知工具: {tool_name}"}
                else:
                    try:
                        tool_result = tool.run(**args)
                    except Exception as e:
                        logger.exception("[Tool Agent] 工具 {} 调用失败", tool_name)
                        tool_result = {"error": str(e)}

            tool_call_records.append(ToolCallRecord(
                name=tool_name,
                kind=tool_kind,
                arguments=args,
                result=tool_result,
            ))

            # 把工具结果追加到 messages
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, ensure_ascii=False),
            })
    else:
        # 超过 MAX_TURNS 还没收敛，强制一次自由回答
        logger.warning("[Tool Agent] function calling 达到最大轮数 {}", MAX_TURNS)
        final_answer = llm.complete(messages=messages, temperature=0.3)

    return {
        "tool_calls": tool_call_records,
        "final_answer": final_answer,
        "execution_trace": append_trace(
            state, "tool_agent", started_at,
            input_summary={"user_input": user_input[:60], "match": "function_calling"},
            output_summary={
                "tool_call_count": len(tool_call_records),
                "tools_used": [r["name"] for r in tool_call_records],
                "answer_preview": final_answer[:80],
            },
        ),
    }


def tool_agent_node(state: AgentState) -> Dict[str, Any]:
    """Tool Agent 入口"""
    started_at = time.time()

    # 阶段 1：优先 Skill
    skill_result = _try_skill(state, started_at)
    if skill_result is not None:
        return skill_result

    # 阶段 2：function calling
    return _function_calling_loop(state, started_at)
