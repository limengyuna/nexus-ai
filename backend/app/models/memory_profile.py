from sqlalchemy import String, Text, Boolean, JSON, ForeignKey, Float, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from typing import Any, Dict, Optional

from app.core.database import Base
from app.models.base import TimestampMixin


class MemorySlot(Base, TimestampMixin):
    __tablename__ = "memory_slots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slot_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    slot_type: Mapped[str] = mapped_column(String(32), index=True)
    value_type: Mapped[str] = mapped_column(String(32), default="string")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserMemorySlotValue(Base, TimestampMixin):
    __tablename__ = "user_memory_slot_values"
    __table_args__ = (
        UniqueConstraint("user_id", "slot_id", name="uq_user_memory_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("memory_slots.id", ondelete="CASCADE"), index=True)
    slot_value: Mapped[Any] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    source: Mapped[str] = mapped_column(String(32), default="inferred")
    source_session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(32), default="assistant")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MemoryCandidate(Base, TimestampMixin):
    __tablename__ = "memory_candidates"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_hash", name="uq_user_candidate"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_text: Mapped[str] = mapped_column(Text)
    suggested_slot_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    suggested_value: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    dedupe_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    source_session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
