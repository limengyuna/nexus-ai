"""
对话会话与消息模型
"""
import enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import JSON, Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class MessageRole(str, enum.Enum):
    """消息角色枚举"""
    USER = "user"            # 用户消息
    ASSISTANT = "assistant"  # AI 助手回复
    SYSTEM = "system"        # 系统消息（如错误提示）


class AgentSource(str, enum.Enum):
    """Agent 来源枚举（标记消息由哪个 Agent 产出）"""
    USER = "user"           # 用户输入
    ROUTER = "router"       # 路由 Agent
    RAG = "rag"             # RAG Agent
    TOOL = "tool"           # Tool/Skill Agent
    SUMMARY = "summary"     # 摘要压缩 Agent


class ChatSession(Base, TimestampMixin):
    """对话会话表"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="新对话",
        comment="会话标题（通常取首条消息前几十字）",
    )

    # LLM 压缩后的历史摘要，作为给 LLM 的精简记忆上下文
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="LLM 压缩的对话摘要",
    )

    # ---------- 关联关系 ----------
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )

    # 可选关联到某个知识库，对话默认基于该知识库做 RAG
    kb_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联的知识库 ID（可选）",
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions")

    messages: Mapped[List["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} title={self.title!r}>"


class ChatMessage(Base, TimestampMixin):
    """对话消息表（保存完整消息记录，与 summary 字段互补）"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    role: Mapped[MessageRole] = mapped_column(
        SAEnum(MessageRole, name="message_role_enum"),
        nullable=False,
        comment="消息角色",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息正文",
    )

    # 标记由哪个 Agent 产出，便于前端展示与调试
    agent_source: Mapped[Optional[AgentSource]] = mapped_column(
        SAEnum(AgentSource, name="agent_source_enum"),
        nullable=True,
        comment="产出该消息的 Agent 来源",
    )

    # 记录工具调用详情（JSON），如 [{"tool": "weather", "args": {...}, "result": "..."}]
    # with_variant 让 SQLite 测试可用；生产 PG 用 JSONB
    tool_calls_json: Mapped[Optional[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
        comment="工具调用详情（JSON）",
    )

    # 任务计划元信息（仅 assistant 消息使用），结构：
    # {"task_plan": [{"step": 1, "agent": "tool_agent", "instruction": "...", "status": "completed"|"cancelled"}, ...],
    #  "interrupted": true|false}
    # 用户取消当前轮次时把 task_plan 持久化到此字段，下一轮 supervisor 规划阶段读取它，
    # 让 LLM 知道哪些 step 已完成、哪些被中断需要重跑——从而避免重复已完成的 step
    task_plan_meta: Mapped[Optional[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
        comment="任务计划元信息：上一轮 task_plan 状态 + 是否被中断（用于跨轮续跑）",
    )

    # 该消息消耗的 Token 数（便于成本统计）
    token_usage: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Token 消耗数",
    )

    # 摘要压缩后的软删除标记（已压缩的旧消息不会从 DB 删除，仅标记，前端可加载完整历史）
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否已被摘要压缩归档",
    )

    # ---------- 关联关系 ----------
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属会话 ID",
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} role={self.role.value} session_id={self.session_id}>"
