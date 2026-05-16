"""
上下文准备节点（中间件模式）

职责：
- 统一从 state 中读取 summary（对话历史摘要）
- 构造标准化的 messages 列表写入 state.messages
- 后续所有节点直接从 state.messages 读取上下文，无需各自处理

设计原则：
- 单一职责：上下文注入逻辑集中在此，新增节点不需要关心上下文怎么来的
- 参考了 LangGraph Checkpointer 的思想 + 中间件/拦截器模式
"""
from typing import Any, Dict

from loguru import logger

from app.agent.state import AgentState


def context_prep_node(state: AgentState) -> Dict[str, Any]:
    """
    统一上下文准备节点。

    读取 state.summary（由 chat_service.py 构造，包含摘要 + 最近对话记录），
    将其转化为标准 messages 格式写入 state.messages，供下游节点直接使用。
    """
    summary = state.get("summary", "")
    user_input = state.get("user_input", "")

    context_messages = []

    # 注入对话历史上下文（长期记忆 + 最近对话）
    if summary:
        context_messages.append({
            "role": "system",
            "content": f"以下是之前的对话上下文，请结合上下文理解用户意图：\n{summary}",
        })
        logger.info("[Context Prep] 注入对话历史上下文（{}字）", len(summary))

    # 注入当前用户输入
    context_messages.append({"role": "user", "content": user_input})

    logger.info("[Context Prep] 构造 {} 条上下文消息", len(context_messages))

    return {"context_messages": context_messages}
