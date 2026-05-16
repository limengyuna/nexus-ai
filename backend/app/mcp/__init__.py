"""
MCP (Model Context Protocol) 协议层

双向集成：
- server: 把内部能力（RAG 检索、知识库查询）按 MCP 协议暴露给外部 MCP 客户端
- client: Agent 内置 MCP Client，可动态连接外部 MCP Server 并调用其工具

MCP 是 Anthropic 提出的开放标准，让 AI 系统能用统一协议互联，
就像 USB 标准让任意外设能即插即用一样。
"""
