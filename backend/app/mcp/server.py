"""
MCP Server：把 NexusAI 的能力暴露为标准 MCP 协议

提供三类原语：
- Resources: 知识库列表（资源访问）
- Tools:     rag_search（RAG 检索）、get_weather、calculate
- Prompts:   rag_qa_template（统一的 RAG 问答提示词模板）

启动方式（stdio 传输，方便接入 Claude Desktop / Cursor 等客户端）::

    python -m app.mcp.server

未来可扩展 SSE/HTTP 传输。
"""
import asyncio
import json
from typing import Any

from loguru import logger
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Prompt,
    PromptArgument,
    Resource,
    TextContent,
    Tool,
)

from app.agent.tools import tool_registry
from app.core.database import SessionLocal
from app.models.knowledge_base import KnowledgeBase
from app.rag.embedder import get_embedder
from app.rag.vector_store import get_vector_store

# 创建 MCP server 实例
mcp_server = Server("nexus-ai")


# ============================================================
# Resources：暴露知识库列表
# ============================================================
@mcp_server.list_resources()
async def list_resources() -> list[Resource]:
    """暴露所有知识库为 MCP Resource"""
    db = SessionLocal()
    try:
        kbs = db.query(KnowledgeBase).all()
        return [
            Resource(
                uri=f"nexus://kb/{kb.id}",
                name=f"知识库: {kb.name}",
                description=kb.description or f"NexusAI 知识库 #{kb.id}",
                mimeType="application/json",
            )
            for kb in kbs
        ]
    finally:
        db.close()


@mcp_server.read_resource()
async def read_resource(uri: str) -> str:
    """读取单个知识库的元数据"""
    # uri 形如 "nexus://kb/3"
    if not uri.startswith("nexus://kb/"):
        raise ValueError(f"未知资源 URI: {uri}")
    kb_id = int(uri.split("/")[-1])

    db = SessionLocal()
    try:
        kb = db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError(f"知识库 {kb_id} 不存在")
        return json.dumps({
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "chunk_strategy": kb.chunk_strategy.value,
            "document_count": len(kb.documents),
            "created_at": kb.created_at.isoformat(),
        }, ensure_ascii=False, indent=2)
    finally:
        db.close()


# ============================================================
# Tools：暴露 RAG 检索 + 已注册的原子工具
# ============================================================
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """暴露 RAG 检索 + 所有 NexusAI 内部工具"""
    tools: list[Tool] = [
        # 平台原生的 RAG 检索工具（专门给外部用）
        Tool(
            name="nexus_rag_search",
            description="在 NexusAI 指定知识库中进行语义检索，返回 top_k 个最相关的文档片段",
            inputSchema={
                "type": "object",
                "properties": {
                    "kb_id": {"type": "integer", "description": "知识库 ID"},
                    "query": {"type": "string", "description": "检索查询"},
                    "top_k": {"type": "integer", "description": "返回结果数", "default": 5},
                },
                "required": ["kb_id", "query"],
            },
        ),
    ]
    # 把内部 Tool 注册中心的工具也都暴露出去
    for t in tool_registry.list():
        schema = t.to_openai_schema()["function"]
        tools.append(Tool(
            name=schema["name"],
            description=schema["description"],
            inputSchema=schema["parameters"],
        ))
    return tools


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """处理工具调用请求"""
    logger.info("[MCP Server] 工具调用: {} args={}", name, arguments)

    # nexus_rag_search 特殊处理
    if name == "nexus_rag_search":
        return await _handle_rag_search(arguments)

    # 其他工具走 tool_registry
    tool = tool_registry.get(name)
    if tool is None:
        return [TextContent(type="text", text=f"未知工具: {name}")]
    try:
        result = tool.run(**arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"工具执行失败: {e}")]


async def _handle_rag_search(arguments: dict[str, Any]) -> list[TextContent]:
    """执行 RAG 检索"""
    kb_id = arguments.get("kb_id")
    query = arguments.get("query", "")
    top_k = arguments.get("top_k", 5)

    db = SessionLocal()
    try:
        kb = db.get(KnowledgeBase, kb_id)
        if kb is None or not kb.collection_name:
            return [TextContent(type="text", text=f"知识库 {kb_id} 不存在或未初始化")]

        embedder = get_embedder()
        vector_store = get_vector_store()
        query_vec = embedder.embed_query(query)
        hits = vector_store.search(
            collection_name=kb.collection_name,
            query_embedding=query_vec,
            top_k=top_k,
        )

        formatted = [
            {
                "rank": i + 1,
                "score": round(h.score, 4),
                "content": h.content,
                "source": h.metadata.get("file_name", "未知"),
                "header_path": h.metadata.get("header_path", ""),
            }
            for i, h in enumerate(hits)
        ]
        return [TextContent(
            type="text",
            text=json.dumps({"query": query, "hits": formatted}, ensure_ascii=False, indent=2),
        )]
    finally:
        db.close()


# ============================================================
# Prompts：可复用的提示词模板
# ============================================================
@mcp_server.list_prompts()
async def list_prompts() -> list[Prompt]:
    return [
        Prompt(
            name="rag_qa_template",
            description="NexusAI 知识库问答标准模板：基于检索结果回答问题，避免幻觉",
            arguments=[
                PromptArgument(name="question", description="用户问题", required=True),
                PromptArgument(name="context", description="检索到的参考资料", required=True),
            ],
        ),
    ]


@mcp_server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> dict:
    if name != "rag_qa_template":
        raise ValueError(f"未知 prompt: {name}")
    arguments = arguments or {}
    question = arguments.get("question", "")
    context = arguments.get("context", "")
    rendered = (
        "你是 NexusAI 知识库问答助手。请基于下面的'参考资料'回答用户问题。\n\n"
        "规则：\n"
        "1. 优先使用参考资料中的内容回答\n"
        "2. 如果资料不足，明确说'根据已有资料无法准确回答'\n"
        "3. 不要编造资料中没有的事实\n\n"
        f"参考资料：\n{context}\n\n"
        f"用户问题：{question}\n"
    )
    return {
        "description": "RAG QA template",
        "messages": [
            {"role": "user", "content": {"type": "text", "text": rendered}}
        ],
    }


# ============================================================
# 启动入口（stdio 传输）
# ============================================================
async def run_stdio():
    """以 stdio 方式启动 MCP server（适合本地客户端如 Claude Desktop）"""
    logger.info("[MCP Server] 启动 stdio 传输")
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(run_stdio())
