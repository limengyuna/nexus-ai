"""
LangGraph 主图编排 — Supervisor 多 Agent 协作架构

拓扑：

    START → context_prep → supervisor ←→ [循环]
                              │              ├── rag_agent → supervisor
                              │              ├── tool_agent → supervisor
                              │              └── FINISH → END
                              └──────────────────────────┘

Supervisor 是调度中心：
- 分析用户意图，决定分发给 RAG Agent / Tool Agent / 自己回答
- 子 Agent 执行完后回到 Supervisor，Supervisor 再决策是否继续
- 支持复合请求："查知识库再写文件" → RAG Agent → Tool Agent → FINISH

设计原则：
- Supervisor 最多循环 3 次，防止无限循环
- 闲聊 / 简单问答由 Supervisor 直接回答，不分发
- done 信号由 Supervisor 决策 FINISH 时发出
"""
from typing import Literal

from langgraph.graph import END, START, StateGraph
from loguru import logger

from app.agent.nodes.context_prep import context_prep_node
from app.agent.nodes.supervisor import supervisor_node, NEXT_RAG, NEXT_TOOL, NEXT_FINISH
from app.agent.nodes.rag_agent import rag_agent_node
from app.agent.nodes.tool_agent import tool_agent_node
from app.agent.state import AgentState


# ---------- 条件边：Supervisor 决策后的路由 ----------
def _supervisor_route(state: AgentState) -> Literal["rag_agent", "tool_agent", "__end__"]:
    """根据 Supervisor 的 next_agent 决策路由"""
    next_agent = state.get("next_agent", NEXT_FINISH)
    if next_agent == NEXT_RAG:
        return "rag_agent"
    if next_agent == NEXT_TOOL:
        return "tool_agent"
    return "__end__"  # FINISH → 结束


# ---------- 图构建 ----------
def build_agent_graph():
    """
    构建并编译 LangGraph Supervisor 工作流。

    返回 compiled graph，可调用 .invoke(state) 或 .stream(state)。
    """
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("context_prep", context_prep_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("tool_agent", tool_agent_node)

    # 入口：START → context_prep → supervisor
    workflow.add_edge(START, "context_prep")
    workflow.add_edge("context_prep", "supervisor")

    # Supervisor 条件路由：决定分发给谁或结束
    workflow.add_conditional_edges(
        "supervisor",
        _supervisor_route,
        {
            "rag_agent": "rag_agent",
            "tool_agent": "tool_agent",
            "__end__": END,
        },
    )

    # 子 Agent 执行完后回到 Supervisor（循环）
    workflow.add_edge("rag_agent", "supervisor")
    workflow.add_edge("tool_agent", "supervisor")

    compiled = workflow.compile()
    logger.info("LangGraph Supervisor 主图编译完成 (节点: context_prep, supervisor, rag_agent, tool_agent; 循环: agent → supervisor)")
    return compiled


# ---------- 单例 ----------
_compiled_graph = None


def get_agent_graph():
    """获取编译后的主图（单例）"""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
    return _compiled_graph
