"""
原子工具层

每个 Tool 是单一原子能力（查天气、做计算等）。
工具注册中心 ToolRegistry 提供：
- 装饰器 @register_tool 自动注册
- get_tool(name) 按名查询
- list_tools() 列出所有工具
- to_openai_schema() 转换为 OpenAI Function Calling 格式（供 LLM Function Calling 用）
"""
from app.agent.tools.registry import (
    BaseTool,
    ToolRegistry,
    get_tool,
    list_tools,
    register_tool,
    tool_registry,
)

# 显式导入触发注册（导入即注册）
from app.agent.tools import business_context, calculator, rag_search, weather, web_search  # noqa: F401

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "register_tool",
    "get_tool",
    "list_tools",
    "tool_registry",
]
