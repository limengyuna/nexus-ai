"""
LangGraph Agent 节点集合 — Supervisor 多 Agent 协作架构

每个节点是一个函数：(state: AgentState) -> dict（只返回需要修改的字段）。
节点之间通过 State 共享数据，由 graph.py 编排执行顺序。

拓扑：context_prep → supervisor ↔ rag_agent / tool_agent
"""
from app.agent.nodes.context_prep import context_prep_node
from app.agent.nodes.supervisor import supervisor_node
from app.agent.nodes.rag_agent import rag_agent_node
from app.agent.nodes.tool_agent import tool_agent_node

from app.agent.nodes.business_context_agent import business_context_agent_node
from app.agent.nodes.synthesis_agent import synthesis_agent_node

__all__ = [
    "context_prep_node",
    "supervisor_node",
    "rag_agent_node",
    "tool_agent_node",
    "business_context_agent_node",
    "synthesis_agent_node",
]
