"""
LangGraph Agent 节点集合

每个节点是一个函数：(state: AgentState) -> dict（只返回需要修改的字段）。
节点之间通过 State 共享数据，由 graph.py 编排执行顺序。
"""
from app.agent.nodes.context_prep import context_prep_node
from app.agent.nodes.fallback import fallback_node
from app.agent.nodes.rag_agent import rag_agent_node
from app.agent.nodes.router import router_node
from app.agent.nodes.tool_agent import tool_agent_node

__all__ = [
    "context_prep_node",
    "router_node",
    "rag_agent_node",
    "tool_agent_node",
    "fallback_node",
]
