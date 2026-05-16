"""
MCP 相关 Schemas
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.mcp_server import MCPTransportType


class MCPServerConfigCreate(BaseModel):
    """创建 MCP Server 连接配置"""
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=1000)
    transport_type: MCPTransportType
    connection_uri: str = Field(..., min_length=1, max_length=512, description="stdio: 命令行；SSE/HTTP: URL")
    env_vars: Optional[Dict[str, str]] = Field(None, description="启动环境变量（仅 stdio）")


class MCPServerConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    transport_type: MCPTransportType
    connection_uri: str
    env_vars: Optional[Dict[str, str]]
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime


class MCPToolInfo(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]


class MCPToolInvokeRequest(BaseModel):
    tool_name: str
    arguments: Optional[Dict[str, Any]] = None


class MCPToolInvokeResponse(BaseModel):
    tool_name: str
    result: Any


class MCPConnectionTestRequest(BaseModel):
    """测试 MCP 连接的请求（不入库）"""
    transport_type: MCPTransportType
    connection_uri: str = Field(..., min_length=1, max_length=512)
    env_vars: Optional[Dict[str, str]] = None


class MCPConnectionTestResponse(BaseModel):
    """测试连接的结果"""
    ok: bool
    tools_count: int
    latency_ms: int
    tools: List[str] = Field(default_factory=list, description="工具名预览（最多 5 个）")
    error: Optional[str] = None
