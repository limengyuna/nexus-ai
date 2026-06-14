"""
异步任务记录模型

用于追踪 Celery 异步任务的执行状态与进度。
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class TaskType(str, enum.Enum):
    """任务类型枚举"""
    DOCUMENT_PROCESS = "document_process"   # 文档处理：解析→分块→向量化
    BATCH_EMBEDDING = "batch_embedding"     # 批量向量化（预留）
    SUMMARY_GENERATE = "summary_generate"   # 对话摘要生成（预留）


class TaskStatus(str, enum.Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    SUCCESS = "success"        # 成功
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消


class TaskRecord(Base, TimestampMixin):
    """异步任务记录表"""

    __tablename__ = "task_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Task owner user ID",
    )

    # Celery 任务 ID（便于反查 Celery 后端结果）
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
        comment="Celery 任务 ID",
    )

    type: Mapped[TaskType] = mapped_column(
        SAEnum(TaskType, name="task_type_enum"),
        nullable=False,
        index=True,
        comment="任务类型",
    )

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status_enum"),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
        comment="任务状态",
    )

    # 关联的业务对象 ID，例如 document_id
    # 不做外键约束，因为可能关联不同类型的对象
    related_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="关联业务对象 ID",
    )

    # 进度百分比 0-100
    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="进度百分比 0-100",
    )

    error_msg: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="失败时的错误信息",
    )

    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="任务结束时间",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskRecord id={self.id} type={self.type.value} "
            f"status={self.status.value} progress={self.progress}%>"
        )
