"""
异步任务相关 Schemas
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus
from app.models.task import TaskStatus, TaskType


class TaskRecordOut(BaseModel):
    """任务记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    celery_task_id: Optional[str]
    type: TaskType
    status: TaskStatus
    detail_status: Optional[DocumentStatus] = None
    related_id: Optional[int]
    progress: int
    error_msg: Optional[str]
    created_at: datetime
    finished_at: Optional[datetime]
