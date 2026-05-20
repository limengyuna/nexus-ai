"""
记忆事实模型模型
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class MemoryFactType(str, enum.Enum):
    """记忆事实类型枚举"""
    ERROR_LESSON = "error_lesson"        # 工具/执行错误教训
    ENV_CONSTRAINT = "env_constraint"    # 环境约束（如操作系统、路径、API约束等）
    PREFERENCE = "preference"            # 用户个人偏好、编码习惯
    KNOWLEDGE = "knowledge"              # 业务知识、概念、关键事实


class MemoryFact(Base, TimestampMixin):
    """L2 语义事实记忆表"""

    __tablename__ = "memory_facts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )

    # 抽取自哪个对话会话，可选（软删除时会设为 NULL，确保记忆持久）
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="来源会话 ID（可选）",
    )

    # 关联的知识库 ID，可选
    # NULL 表示全局记忆（如用户偏好），非 NULL 表示知识库专属记忆（如某项目的环境约束）
    kb_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联知识库 ID（NULL 为全局记忆）",
    )

    fact_type: Mapped[MemoryFactType] = mapped_column(
        SAEnum(MemoryFactType, name="memory_fact_type_enum"),
        nullable=False,
        default=MemoryFactType.KNOWLEDGE,
        comment="记忆事实类型",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="记忆事实文本内容",
    )

    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        comment="重要性评分（0.0 ~ 1.0）",
    )

    access_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="被检索并采用的次数",
    )

    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最后一次被检索访问时间",
    )

    # ---------- 关联关系 ----------
    user = relationship("User", backref="memory_facts")
    session = relationship("ChatSession")

    def __repr__(self) -> str:
        return f"<MemoryFact id={self.id} user_id={self.user_id} type={self.fact_type.value}>"
