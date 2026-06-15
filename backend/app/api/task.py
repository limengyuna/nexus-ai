"""
异步任务进度查询 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.task import TaskType
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.task import TaskRecordOut
from app.services.document_service import TaskService

router = APIRouter(prefix="/tasks", tags=["异步任务"])


@router.get(
    "/{task_id}",
    response_model=ApiResponse[TaskRecordOut],
    summary="查询任务执行进度",
)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """前端轮询此接口获取异步任务的实时进度与状态"""
    task = TaskService.get_for_user(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        
    out = TaskRecordOut.model_validate(task)
    
    # 若是文档处理任务，查出具体的阶段状态并注入
    if task.type == TaskType.DOCUMENT_PROCESS and task.related_id:
        from app.models.document import Document
        doc = db.get(Document, task.related_id)
        if doc:
            out.detail_status = doc.status.value
            
    return ApiResponse.ok(data=out)
