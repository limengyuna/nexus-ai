"""
Agent 模块：LangGraph 多 Agent 协作引擎

四层架构：
- llm:      LLM 客户端封装（DeepSeek，OpenAI 兼容接口）
- state:    AgentState 共享状态（含 execution_trace 链路追踪）
- tools:    原子工具层（注册中心 + 具体工具实现）
- skills:   技能编排层（多 Tool + Prompt 组合）
- nodes:    Agent 节点（Router / RAG / Tool）
- graph:    LangGraph 主图编排
"""
