"""
MCP（Model Context Protocol）外部 Server 配置模型

存储管理员配置的外部 MCP Server 连接信息，
供 MCP Client 在运行时动态连接并发现外部工具。
"""
import enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class MCPTransportType(str, enum.Enum):
    """MCP 传输协议类型"""
    STDIO = "stdio"   # 标准输入输出（本地子进程方式，如 npx 启动）
    SSE = "sse"       # Server-Sent Events（远程 HTTP）
    HTTP = "http"     # Streamable HTTP（MCP 最新协议）


class MCPServerConfig(Base, TimestampMixin):
    """外部 MCP Server 连接配置表"""

    __tablename__ = "mcp_server_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
        comment="MCP Server 显示名（唯一）",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="描述用途",
    )

    transport_type: Mapped[MCPTransportType] = mapped_column(
        SAEnum(MCPTransportType, name="mcp_transport_enum"),
        nullable=False,
        comment="传输协议类型",
    )

    # stdio 传输：连接命令，如 "npx -y @modelcontextprotocol/server-github"
    # SSE/HTTP 传输：远程 URL，如 "http://example.com/mcp"
    connection_uri: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="连接命令或 URL",
    )

    # 额外的环境变量（如 API Key），仅 stdio 传输有用
    # 例：{"GITHUB_TOKEN": "ghp_xxx"}
    # 用 with_variant 保证 SQLite（测试用）兼容；生产 PG 仍走 JSONB 享受索引/查询能力
    env_vars: Mapped[Optional[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
        comment="启动环境变量（JSON）",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用",
    )

    # 缓存子工具列表（测试连接/刷新时写入）
    # 格式: [{"name": "...", "description": "...", "inputSchema": {...}}, ...]
    cached_tools: Mapped[Optional[list]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
        comment="缓存的子工具清单（JSON Array）",
    )

    tool_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        server_default="0",
        comment="子工具数量",
    )

    # ---------- 关联关系 ----------
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="创建人 ID",
    )

    creator: Mapped["User"] = relationship(
        back_populates="mcp_configs",
        foreign_keys=[created_by],
    )

    def __repr__(self) -> str:
        return f"<MCPServerConfig id={self.id} name={self.name!r} transport={self.transport_type.value}>"
