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
import sys
import asyncio
import threading
import time
from concurrent.futures import Future
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.mcp_server import MCPServerConfig, MCPTransportType


def _run_in_proactor_thread(coro):
    """
    Windows 专属桥接器：
    当使用 uvicorn --reload 开发模式启动时，事件循环会被强行修改为 SelectorEventLoop。
    该循环在 Windows 下不支持子进程管道，会导致 stdio 形式的 MCP 启动失败（NotImplementedError）。
    这里启动一个临时的 ProactorEventLoop 线程来安全运行子进程，并把结果桥接回主 Selector 线程。
    """
    current_loop = None
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    # 仅在 Windows 且当前运行着 SelectorEventLoop 时启动线程桥接
    if sys.platform == "win32" and current_loop and current_loop.__class__.__name__ == "_WindowsSelectorEventLoop":
        logger.info("[MCP Client] 检测到 Windows SelectorEventLoop，启动 WindowsProactorEventLoop 线程进行桥接...")
        future = Future()

        def _target():
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(coro)
                future.set_result(res)
            except Exception as e:
                future.set_exception(e)
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        return asyncio.wrap_future(future)
    else:
        # 其他系统或已经是 Proactor 循环时，直接正常 await
        return coro



async def _default_list_roots(context) -> Any:
    """默认的 roots 列出回调，防止支持 roots 要求的 MCP Server 握手时卡死超时"""
    import mcp.types as mcp_types
    return mcp_types.ListRootsResult(roots=[])


# ---------- 内部：建立 MCP Client Session ----------
@asynccontextmanager
async def _open_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
    """
    根据配置建立 MCP Client Session（上下文管理器，自动清理）
    """
    if config.transport_type == MCPTransportType.STDIO:
        # connection_uri 形如 "npx -y @modelcontextprotocol/server-github"
        parts = config.connection_uri.split()
        command = parts[0]
        args = parts[1:]
        
        # Windows 下 npx/node 等命令实际是 .cmd 批处理文件，
        # asyncio subprocess_exec 不走 shell，不会自动解析 .cmd 后缀
        if sys.platform == "win32":
            import shutil
            resolved = shutil.which(command)
            if resolved:
                # 优先使用 shutil.which 解析出的绝对路径（例如 C:\Program Files\nodejs\npx.cmd）
                command = resolved
            elif not command.endswith(".cmd"):
                command = command + ".cmd"
                
            # 针对 Windows 上的 npx 提速：如果使用了 npx，且参数中没有 --prefer-offline，则自动注入
            # 这可以强制 npm 优先使用本地缓存，避免每次启动都耗费 40s 联网查询和下载临时包
            if "npx" in command.lower() and "--prefer-offline" not in [a.lower() for a in args]:
                # 插入到最前面
                args.insert(0, "--prefer-offline")
                
        # 合并系统环境变量 + 用户配置的 env_vars，避免丢失 PATH 等关键变量
        merged_env = {**os.environ}
        if config.env_vars:
            merged_env.update(config.env_vars)
        params = StdioServerParameters(
            command=command,
            args=args,
            env=merged_env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, list_roots_callback=_default_list_roots) as session:
                await session.initialize()
                yield session

    elif config.transport_type == MCPTransportType.SSE:
        async with sse_client(config.connection_uri) as (read, write):
            async with ClientSession(read, write, list_roots_callback=_default_list_roots) as session:
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

    async def _impl():
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

    try:
        return await _run_in_proactor_thread(_impl())
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

    async def _impl():
        async with _open_session(config) as session:
            result = await session.call_tool(tool_name, arguments)
            contents = []
            for item in result.content:
                if hasattr(item, "text"):
                    contents.append(item.text)
                else:
                    contents.append(str(item))
            
            joined_text = "\n".join(contents) if len(contents) > 1 else (contents[0] if contents else "")
            return {
                "isError": getattr(result, "isError", False),
                "text": joined_text,
                "content": [str(c) for c in result.content]
            }

    return await _run_in_proactor_thread(_impl())



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

    async def _impl():
        async with _open_session(temp_config) as session:
            tools_resp = await session.list_tools()
            return tools_resp.tools

    try:
        tools = await _run_in_proactor_thread(_impl())
        elapsed_ms = int((time.time() - start) * 1000)
        logger.info(
            "[MCP Client] test_connection 成功: {} 个工具, {}ms",
            len(tools), elapsed_ms,
        )
        # 返回完整工具详情供前端展示和缓存
        tools_detail = [
            {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema}
            for t in tools
        ]
        return {
            "ok": True,
            "tools_count": len(tools),
            "latency_ms": elapsed_ms,
            "tools": [t.name for t in tools[:5]],
            "tools_detail": tools_detail,
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
            "tools_detail": [],
            "error": str(e),
        }


async def generate_mcp_description(server_name: str, tools_detail: List[Dict[str, Any]]) -> str:
    """
    用 LLM 根据 MCP Server 名称和子工具列表生成简洁的整体描述。
    该描述将用于 Supervisor 粗粒度选择。
    """
    from app.agent.llm import get_llm_fast

    # 构造工具摘要
    tool_summary = "\n".join(
        f"- {t['name']}: {t.get('description', '无描述')}"
        for t in tools_detail[:20]  # 最多取 20 个防止 prompt 过长
    )

    prompt = f"""根据以下 MCP Server 的名称和它提供的工具列表，生成一句简洁的中文描述（30-80字），说明这个 MCP 服务整体能做什么。

MCP Server 名称：{server_name}
包含的工具：
{tool_summary}

要求：
- 描述应概括这个 MCP 的核心能力
- 不需要列出具体工具名
- 使用自然语言，简洁明了
- 只输出描述文字，不加引号或额外格式"""

    try:
        llm = get_llm_fast()
        resp_text, _ = llm.complete_counted(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        return resp_text.strip()
    except Exception as e:
        logger.warning("[MCP Client] LLM 生成描述失败: {}", e)
        # 降级：用工具名拼接
        tool_names = [t["name"] for t in tools_detail[:5]]
        return f"提供 {', '.join(tool_names)} 等 {len(tools_detail)} 个工具"

