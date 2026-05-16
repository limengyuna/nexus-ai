"""
用户模型
"""
import enum
from typing import TYPE_CHECKING, List

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    # 仅在类型检查时导入，避免运行时循环引用
    from app.models.chat import ChatSession
    from app.models.knowledge_base import KnowledgeBase
    from app.models.mcp_server import MCPServerConfig


class UserRole(str, enum.Enum):
    """用户角色枚举"""
    ADMIN = "admin"   # 管理员：可管理知识库、MCP 配置等
    USER = "user"     # 普通用户：仅能对话


class User(Base, TimestampMixin):
    """用户表"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="用户名（唯一）",
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt 哈希后的密码",
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role_enum"),
        default=UserRole.USER,
        nullable=False,
        comment="用户角色",
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="是否启用",
    )

    # ---------- 关联关系 ----------
    chat_sessions: Mapped[List["ChatSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    knowledge_bases: Mapped[List["KnowledgeBase"]] = relationship(
        back_populates="creator",
        foreign_keys="KnowledgeBase.created_by",
    )

    mcp_configs: Mapped[List["MCPServerConfig"]] = relationship(
        back_populates="creator",
        foreign_keys="MCPServerConfig.created_by",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"
