import json
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from mcp.server import Server
import mcp.types as types
from mcp.server.sse import SseServerTransport

from tools import (
    search_repositories_tool,
    get_repository_info_tool,
    get_repository_readme_tool,
    list_repository_issues_tool,
)

# ---------- 1. 初始化 MCP 官方 Server ----------
mcp_server = Server("github-readonly-mcp")


# ---------- 2. 声明动态工具发现 (list_tools) ----------
@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    暴露只读 GitHub 集成工具清单供 NexusAI 主站动态捕获和注册
    """
    return [
        types.Tool(
            name="search_github_repositories",
            description=(
                "Search public GitHub repositories by keyword. Read-only. "
                "Returns compact repository metadata including stars, forks, language, and URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，例如 'fastapi rag' 或 'langgraph'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量，默认 5，最大限制 10",
                        "default": 5
                    },
                    "sort": {
                        "type": "string",
                        "description": "排序依据，可选 'stars', 'updated', 或 'forks'，默认为 'stars'",
                        "default": "stars"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_repository_info",
            description="Retrieve metadata, settings and metrics of a specific public GitHub repository. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "GitHub 账号所有者，例如 'limengyuna'"
                    },
                    "repo": {
                        "type": "string",
                        "description": "GitHub 仓库名称，例如 'nexus-ai'"
                    }
                },
                "required": ["owner", "repo"]
            }
        ),
        types.Tool(
            name="get_repository_readme",
            description=(
                "Get and read the README.md content of a specific public GitHub repository. "
                "Read-only and content is truncated for context safety."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "GitHub 账号所有者"
                    },
                    "repo": {
                        "type": "string",
                        "description": "GitHub 仓库名称"
                    }
                },
                "required": ["owner", "repo"]
            }
        ),
        types.Tool(
            name="list_repository_issues",
            description=(
                "List open or closed issues of a specific public GitHub repository. "
                "Read-only, automatically excludes Pull Requests."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "GitHub 账号所有者"
                    },
                    "repo": {
                        "type": "string",
                        "description": "GitHub 仓库名称"
                    },
                    "state": {
                        "type": "string",
                        "description": "Issue 的状态，可选为 'open', 'closed' 或 'all'，默认为 'open'",
                        "default": "open"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回 Issue 数量限制，默认 5，最大限制 10",
                        "default": 5
                    }
                },
                "required": ["owner", "repo"]
            }
        )
    ]


# ---------- 3. 声明工具调用适配器 (call_tool) ----------
@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """
    处理大模型规划发起的物理工具执行调用请求
    """
    args = arguments or {}
    logger.info("[MCP Main] 收到执行请求: name={}, args={}", name, args)

    if name == "search_github_repositories":
        res = await search_repositories_tool(
            query=args.get("query", ""),
            sort=args.get("sort", "stars"),
            limit=args.get("limit", 5)
        )
    elif name == "get_repository_info":
        res = await get_repository_info_tool(
            owner=args.get("owner", ""),
            repo=args.get("repo", "")
        )
    elif name == "get_repository_readme":
        res = await get_repository_readme_tool(
            owner=args.get("owner", ""),
            repo=args.get("repo", "")
        )
    elif name == "list_repository_issues":
        res = await list_repository_issues_tool(
            owner=args.get("owner", ""),
            repo=args.get("repo", ""),
            state=args.get("state", "open"),
            limit=args.get("limit", 5)
        )
    else:
        res = {"error": {"code": "tool_not_found", "message": f"未找到指定的外部工具: {name}", "status": 404}}

    # 序列化为 MCP 标准文本内容返回
    return [types.TextContent(type="text", text=json.dumps(res, ensure_ascii=False))]


# ---------- 4. 创建 FastAPI 实例并直接桥接底层 ASGI 路由 ----------
app = FastAPI(
    title="GitHub Readonly MCP SSE Server",
    description="专门为 NexusAI 线上公开演示环境设计的只读 GitHub 代理 MCP 服务",
    version="1.0.0"
)

# 初始化标准 SSE 传输控制器，并指定消息投递的 POST 路径为 /messages
sse_transport = SseServerTransport("/messages")


class MCPSseApp:
    """
    符合 ASGI 协议的 SSE 长连接网关服务
    """
    async def __call__(self, scope, receive, send):
        async with sse_transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
            # 将运行环境与 MCP 核心 Server 绑定
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options()
            )


class MCPMessagesApp:
    """
    符合 ASGI 协议的客户端消息消费网关服务
    """
    async def __call__(self, scope, receive, send):
        await sse_transport.handle_post_message(scope, receive, send)


# 引入 Starlette 的底层 Route 对象
from starlette.routing import Route

# 将类实例作为标准的 ASGI 应用程序，追加注册到最底层的路由表中
app.routes.append(Route("/sse", endpoint=MCPSseApp(), methods=["GET"]))
app.routes.append(Route("/messages", endpoint=MCPMessagesApp(), methods=["POST"]))


@app.get("/health", summary="健康自检接口")
def health_check():
    """用于 Railway 等云平台自检健康状况，确认服务是否处于活动状态"""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "healthy", "service": "github-readonly-mcp"}
    )
