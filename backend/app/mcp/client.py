"""
MCP Client：让 Agent 动态调用外部 MCP Server 的工具

工作流程：
1. 从数据库 MCPServerConfig 表读取已配置的 MCP Server 列表
2. 用 mcp SDK 通过 stdio 或 SSE 连接到外部 Server
3. 调 list_tools() 拉取它们的工具清单
4. 把这些远程工具适配进我们的 ToolRegistry（动态注册）

注：由于网络 + 子进程开销，连接是按需建立的，不在启动时全量连接。
本文件提供两个层级 API：
- list_external_tools(config_id):   按配置 ID 列出外部 Server 的工具清单
- invoke_external_tool(config_id, tool_name, args): 调用一个外部工具
"""
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.mcp_server import MCPServerConfig, MCPTransportType


# ---------- 内部：建立 MCP Client Session ----------
@asynccontextmanager
async def _open_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
    """
    根据配置建立 MCP Client Session（上下文管理器，自动清理）
    """
    if config.transport_type == MCPTransportType.STDIO:
        # connection_uri 形如 "npx -y @modelcontextprotocol/server-github"
        parts = config.connection_uri.split()
        # 合并系统环境变量 + 用户配置的 env_vars，避免丢失 PATH 等关键变量
        merged_env = None
        if config.env_vars:
            merged_env = {**os.environ, **config.env_vars}
        params = StdioServerParameters(
            command=parts[0],
            args=parts[1:],
            env=merged_env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    elif config.transport_type == MCPTransportType.SSE:
        async with sse_client(config.connection_uri) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        raise NotImplementedError(
            f"暂未支持的传输类型: {config.transport_type}（"
            f"MCP SDK 仍在演进，HTTP streamable 待后续支持）"
        )


# ---------- 公共 API ----------
async def list_external_tools(config_id: int) -> List[Dict[str, Any]]:
    """
    列出某外部 MCP Server 的全部工具

    :return: [{"name": "...", "description": "...", "inputSchema": {...}}, ...]
    """
    db: Session = SessionLocal()
    try:
        config = db.get(MCPServerConfig, config_id)
        if config is None:
            raise ValueError(f"MCP 配置 {config_id} 不存在")
        if not config.is_active:
            raise ValueError(f"MCP 配置 {config_id} 已禁用")
    finally:
        db.close()

    logger.info("[MCP Client] 连接外部 server: {} ({})", config.name, config.transport_type.value)

    try:
        async with _open_session(config) as session:
            tools_resp = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema,
                }
                for t in tools_resp.tools
            ]
            logger.info("[MCP Client] 拉到 {} 个外部工具: {}", len(tools), [t["name"] for t in tools])
            return tools
    except Exception as e:
        logger.exception("[MCP Client] list_tools 失败")
        raise RuntimeError(f"连接外部 MCP Server 失败: {e}")


async def invoke_external_tool(
    config_id: int,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    调用某外部 MCP Server 上的指定工具

    :return: 工具返回内容（字符串或结构化数据）
    """
    db: Session = SessionLocal()
    try:
        config = db.get(MCPServerConfig, config_id)
        if config is None:
            raise ValueError(f"MCP 配置 {config_id} 不存在")
        if not config.is_active:
            raise ValueError(f"MCP 配置 {config_id} 已禁用")
    finally:
        db.close()

    arguments = arguments or {}
    logger.info("[MCP Client] 调用外部工具 {} on {} args={}", tool_name, config.name, arguments)

    async with _open_session(config) as session:
        result = await session.call_tool(tool_name, arguments)
        # result.content 是 list[TextContent | ImageContent | ...]
        contents = []
        for item in result.content:
            if hasattr(item, "text"):
                contents.append(item.text)
            else:
                contents.append(str(item))
        return "\n".join(contents) if len(contents) > 1 else (contents[0] if contents else "")


# ---------- 测试连接（不需要先入库）----------
async def test_connection(
    transport_type: MCPTransportType,
    connection_uri: str,
    env_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    临时建立 MCP 连接并列出工具，用于"创建前先验证"

    :return: {
        "ok": bool,            # 是否连接成功
        "tools_count": int,    # 拉到几个工具
        "latency_ms": int,     # 从开始连接到完成 list_tools 的耗时
        "tools": List[str],    # 前 5 个工具名（预览用）
        "error": Optional[str] # 失败时的错误信息
    }
    """
    # 临时伪造一个未入库的 config 对象给 _open_session 用
    # 直接构造内存版 MCPServerConfig 即可（仅访问几个属性）
    temp_config = MCPServerConfig(
        name="__test__",
        transport_type=transport_type,
        connection_uri=connection_uri,
        env_vars=env_vars,
        is_active=True,
    )

    start = time.time()
    try:
        async with _open_session(temp_config) as session:
            tools_resp = await session.list_tools()
            tools = tools_resp.tools
            elapsed_ms = int((time.time() - start) * 1000)
            logger.info(
                "[MCP Client] test_connection 成功: {} 个工具, {}ms",
                len(tools), elapsed_ms,
            )
            return {
                "ok": True,
                "tools_count": len(tools),
                "latency_ms": elapsed_ms,
                "tools": [t.name for t in tools[:5]],
                "error": None,
            }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.warning("[MCP Client] test_connection 失败: {}", e)
        return {
            "ok": False,
            "tools_count": 0,
            "latency_ms": elapsed_ms,
            "tools": [],
            "error": str(e),
        }
