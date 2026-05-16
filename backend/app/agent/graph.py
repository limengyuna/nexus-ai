"""
LangGraph 主图编排

拓扑：

    START → context_prep → router → [条件路由]
                                      ├── rag      → END
                                      ├── tool     → END
                                      └── chitchat → END

未来扩展点：
- 在 rag/tool 之后加 "reflector" 节点做答案质量自检
- 在 chitchat 后加 interrupt_before 做人工审批（Human-in-the-loop）
"""
from typing import Literal

from langgraph.graph import END, START, StateGraph
from loguru import logger

from app.agent.nodes import context_prep_node, fallback_node, rag_agent_node, router_node, tool_agent_node
from app.agent.nodes.router import ROUTE_CHITCHAT, ROUTE_RAG, ROUTE_TOOL
from app.agent.state import AgentState


# ---------- 条件边：按 intent 分发 ----------
def _route_by_intent(state: AgentState) -> Literal["rag_agent", "tool_agent", "fallback"]:
    """从 Router 出来后，按 intent 选择下游节点"""
    intent = state.get("intent", ROUTE_CHITCHAT)
    if intent == ROUTE_RAG:
        return "rag_agent"
    if intent == ROUTE_TOOL:
        return "tool_agent"
    return "fallback"  # chitchat 或未知 intent 走 fallback


# ---------- 图构建 ----------
def build_agent_graph():
    """
    构建并编译 LangGraph 工作流。

    返回 compiled graph，可调用 .invoke(state) 或 .stream(state)。
    """
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("context_prep", context_prep_node)
    workflow.add_node("router", router_node)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("tool_agent", tool_agent_node)
    workflow.add_node("fallback", fallback_node)

    # 入口：从 START 进入 context_prep，再到 router
    workflow.add_edge(START, "context_prep")
    workflow.add_edge("context_prep", "router")

    # 条件路由
    workflow.add_conditional_edges(
        "router",
        _route_by_intent,
        {
            "rag_agent": "rag_agent",
            "tool_agent": "tool_agent",
            "fallback": "fallback",
        },
    )

    # 终止：三个分支都直接到 END
    workflow.add_edge("rag_agent", END)
    workflow.add_edge("tool_agent", END)
    workflow.add_edge("fallback", END)

    compiled = workflow.compile()
    logger.info("LangGraph 主图编译完成 (节点: context_prep, router, rag_agent, tool_agent, fallback)")
    return compiled


# ---------- 单例 ----------
_compiled_graph = None


def get_agent_graph():
    """获取编译后的主图（单例）"""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
    return _compiled_graph
