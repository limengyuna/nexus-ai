"""
MCP 外部 Server 配置 + 调用 API

接口：
- POST   /mcp/servers              新建外部 MCP Server 配置
- GET    /mcp/servers              列出所有配置
- DELETE /mcp/servers/{id}         删除配置
- GET    /mcp/servers/{id}/tools   列出该外部 server 暴露的工具（实时连接拉取）
- POST   /mcp/servers/{id}/invoke  调用外部工具
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.mcp.client import invoke_external_tool, list_external_tools, test_connection
from app.models.mcp_server import MCPServerConfig
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.mcp import (
    MCPConnectionTestRequest,
    MCPConnectionTestResponse,
    MCPServerConfigCreate,
    MCPServerConfigOut,
    MCPToolInfo,
    MCPToolInvokeRequest,
    MCPToolInvokeResponse,
)

router = APIRouter(prefix="/mcp/servers", tags=["MCP 外部服务"])


@router.post(
    "/test",
    response_model=ApiResponse[MCPConnectionTestResponse],
    summary="测试 MCP 连接（创建前先试一下）",
)
async def test_mcp_connection(
    payload: MCPConnectionTestRequest,
    current_user: User = Depends(get_current_user),
):
    """
    临时连接外部 MCP Server 并列出工具，验证 connection_uri / env_vars 是否正确。
    不会在数据库创建任何记录。
    """
    result = await test_connection(
        transport_type=payload.transport_type,
        connection_uri=payload.connection_uri,
        env_vars=payload.env_vars,
    )
    return ApiResponse.ok(
        data=MCPConnectionTestResponse(**result),
        message="连接成功" if result["ok"] else "连接失败",
    )


@router.post(
    "",
    response_model=ApiResponse[MCPServerConfigOut],
    summary="新建外部 MCP Server 配置",
    status_code=status.HTTP_201_CREATED,
)
def create_mcp_config(
    payload: MCPServerConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 同名检查只在当前用户范围内（允许不同用户同名配置）
    existing = (
        db.query(MCPServerConfig)
        .filter(MCPServerConfig.name == payload.name, MCPServerConfig.created_by == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"名称 '{payload.name}' 已被占用",
        )
    config = MCPServerConfig(
        name=payload.name,
        description=payload.description,
        transport_type=payload.transport_type,
        connection_uri=payload.connection_uri,
        env_vars=payload.env_vars,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return ApiResponse.ok(data=MCPServerConfigOut.model_validate(config), message="已创建")


@router.get(
    "",
    response_model=ApiResponse[List[MCPServerConfigOut]],
    summary="列出所有 MCP Server 配置",
)
def list_mcp_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 多租户隔离：只列出当前用户创建的
    configs = (
        db.query(MCPServerConfig)
        .filter(MCPServerConfig.created_by == current_user.id)
        .order_by(MCPServerConfig.created_at.desc())
        .all()
    )
    return ApiResponse.ok(data=[MCPServerConfigOut.model_validate(c) for c in configs])


@router.delete(
    "/{config_id}",
    response_model=ApiResponse[None],
    summary="删除 MCP 配置",
)
def delete_mcp_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = db.get(MCPServerConfig, config_id)
    if config is None or config.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")
    db.delete(config)
    db.commit()
    return ApiResponse.ok(message="已删除")


@router.get(
    "/{config_id}/tools",
    response_model=ApiResponse[List[MCPToolInfo]],
    summary="实时拉取外部 Server 的工具清单",
)
async def list_tools_of(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """实时连接外部 MCP Server 并 list_tools。注意：可能涉及子进程启动，响应可能略慢。"""
    # 多租户隔离：先验证配置是当前用户的
    config = db.get(MCPServerConfig, config_id)
    if config is None or config.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")
    try:
        tools = await list_external_tools(config_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return ApiResponse.ok(data=[MCPToolInfo(**t) for t in tools])


@router.post(
    "/{config_id}/invoke",
    response_model=ApiResponse[MCPToolInvokeResponse],
    summary="调用某外部 MCP 工具",
)
async def invoke_tool(
    config_id: int,
    payload: MCPToolInvokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 多租户隔离
    config = db.get(MCPServerConfig, config_id)
    if config is None or config.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")
    try:
        result = await invoke_external_tool(config_id, payload.tool_name, payload.arguments)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return ApiResponse.ok(
        data=MCPToolInvokeResponse(tool_name=payload.tool_name, result=result),
    )
