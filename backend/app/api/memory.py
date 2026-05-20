"""
L2 记忆管理 API

提供记忆 facts 的查询与删除接口，支持用户手动清除或校正不当记忆。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.memory import MemoryFact
from app.schemas.common import ApiResponse
from app.schemas.memory import MemoryFactOut
from app.memory.store import MemoryStore

router = APIRouter(prefix="/memory", tags=["长期记忆 (L2)"])


@router.get(
    "/facts",
    response_model=ApiResponse[List[MemoryFactOut]],
    summary="获取当前用户的所有长期事实记忆",
)
def list_memory_facts(
    fact_type: Optional[str] = None,
    kb_id: Optional[int] = None,
    scope: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    列出当前登录用户的长期记忆 facts，支持按类型和知识库过滤。
    
    :param fact_type: 按事实类型过滤（error_lesson / env_constraint / preference / knowledge）
    :param kb_id: 按关联知识库 ID 过滤
    :param scope: "global" 仅全局记忆，"kb" 仅知识库专属记忆，不传则返回全部
    """
    query = db.query(MemoryFact).filter(MemoryFact.user_id == current_user.id)
    
    if fact_type:
        query = query.filter(MemoryFact.fact_type == fact_type)
    
    if kb_id is not None:
        query = query.filter(MemoryFact.kb_id == kb_id)
    elif scope == "global":
        query = query.filter(MemoryFact.kb_id.is_(None))
    elif scope == "kb":
        query = query.filter(MemoryFact.kb_id.isnot(None))
        
    facts = query.order_by(MemoryFact.importance.desc(), MemoryFact.id.desc()).all()
    
    return ApiResponse.ok(
        data=[MemoryFactOut.model_validate(f) for f in facts]
    )


@router.delete(
    "/facts/{fact_id}",
    response_model=ApiResponse[bool],
    summary="删除指定 ID 的长期事实记忆",
)
def delete_memory_fact(
    fact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除一条特定的事实记忆（包括 PostgreSQL 中的记录和 ChromaDB 中的向量索引）。
    加入了防越权校验，只有记忆的主人才能进行删除。
    """
    # 1. 越权防范：查询事实，确保存在且属于当前登录用户
    fact = db.get(MemoryFact, fact_id)
    if not fact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该事实记忆不存在"
        )
        
    if fact.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您无权删除他人的记忆事实"
        )
        
    # 2. 调用管理器执行 PostgreSQL & ChromaDB 级联删除
    success = MemoryStore.delete_fact(db, fact_id)
    if not success:
        return ApiResponse.fail(message="删除失败", code=500)
        
    return ApiResponse.ok(data=True, message="成功删除该记忆事实")
