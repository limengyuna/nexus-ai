from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.memory_profile import (
    UserProfileResponse,
    ProfileSlotItem,
    UpdateProfileSlotRequest,
    MemoryCandidateItem,
    MemoryCandidateListResponse,
    AcceptCandidateRequest
)
from app.memory.profile_store import MemoryProfileStore

router = APIRouter(prefix="/memory/profile", tags=["结构化档案 (Profile Slots)"])


@router.get(
    "",
    response_model=ApiResponse[UserProfileResponse],
    summary="获取当前用户的结构化档案",
)
def get_user_profile(
    slot_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户的结构化档案，可按 slot_type 过滤。"""
    slot_types = [slot_type] if slot_type else None
    values = MemoryProfileStore.get_user_profile(db, current_user.id, slot_types)
    
    # 转换为 API 响应格式 (由于通过 join 查询，实际的 model 里并没有 slot_type，所以需要手动拼)
    # 在实际的 SQLAlchemy 中，如果对象是从 join 中拿出的，可能无法直接访问关联对象的属性。
    # 我们为了简单，重新再包一下，或者在 ORM 模型里定义 relationship。
    # 这里我们采用在 DB 查询出对应的 MemorySlot。
    
    from app.models.memory_profile import MemorySlot
    from sqlalchemy import select
    
    slots_map = {
        s.id: s for s in db.execute(select(MemorySlot)).scalars().all()
    }
    
    items = []
    for val in values:
        slot = slots_map.get(val.slot_id)
        if slot:
            items.append(ProfileSlotItem(
                slot_key=slot.slot_key,
                slot_type=slot.slot_type,
                slot_value=val.slot_value,
                confidence=val.confidence,
                source=val.source,
                updated_at=val.updated_at
            ))
            
    return ApiResponse.ok(data=UserProfileResponse(profile=items))


@router.put(
    "/{slot_key}",
    response_model=ApiResponse[ProfileSlotItem],
    summary="手动更新档案槽位",
)
def update_profile_slot(
    slot_key: str,
    request: UpdateProfileSlotRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """用户手动写入/更新偏好，优先级最高。"""
    val = MemoryProfileStore.upsert_slot_value(
        db=db,
        user_id=current_user.id,
        slot_key=slot_key,
        slot_value=request.slot_value,
        confidence=1.0,
        source=request.source,
        updated_by="user"
    )
    
    if not val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该槽位暂不可用或未启用"
        )
        
    from app.models.memory_profile import MemorySlot
    from sqlalchemy import select
    slot = db.execute(select(MemorySlot).where(MemorySlot.id == val.slot_id)).scalar_one()

    item = ProfileSlotItem(
        slot_key=slot.slot_key,
        slot_type=slot.slot_type,
        slot_value=val.slot_value,
        confidence=val.confidence,
        source=val.source,
        updated_at=val.updated_at
    )
    return ApiResponse.ok(data=item)


@router.delete(
    "/{slot_key}",
    response_model=ApiResponse[bool],
    summary="删除档案槽位",
)
def delete_profile_slot(
    slot_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """用户手动清除偏好记录。"""
    success = MemoryProfileStore.delete_slot_value(db, current_user.id, slot_key)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到相关的槽位记录"
        )
    return ApiResponse.ok(data=True)


@router.get(
    "/candidates",
    response_model=ApiResponse[MemoryCandidateListResponse],
    summary="获取当前用户的候选偏好列表",
)
def get_candidates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户状态为 pending 的候选偏好。"""
    from app.models.memory_profile import MemoryCandidate
    from sqlalchemy import select
    
    candidates = db.execute(
        select(MemoryCandidate)
        .where(MemoryCandidate.user_id == current_user.id, MemoryCandidate.status == "pending")
        .order_by(MemoryCandidate.confidence.desc())
    ).scalars().all()
    
    items = [MemoryCandidateItem.model_validate(c) for c in candidates]
    return ApiResponse.ok(data=MemoryCandidateListResponse(candidates=items))


@router.post(
    "/candidates/{candidate_id}/accept",
    response_model=ApiResponse[ProfileSlotItem],
    summary="接受/采纳候选偏好",
)
def accept_candidate(
    candidate_id: int,
    request: AcceptCandidateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """采纳候选偏好，将其同步转正为正式的结构化用户档案槽位值。"""
    from app.models.memory_profile import MemoryCandidate, MemorySlot
    from sqlalchemy import select
    
    candidate = db.execute(
        select(MemoryCandidate)
        .where(MemoryCandidate.id == candidate_id, MemoryCandidate.user_id == current_user.id)
    ).scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该候选偏好记录"
        )
        
    if candidate.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该候选偏好已处理过"
        )
        
    # 确定转正时的值
    final_value = request.slot_value if request.slot_value is not None else candidate.suggested_value
    if final_value is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未提供有效的槽位建议值"
        )
        
    if not candidate.suggested_slot_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="候选偏好的槽位键（slot_key）无效"
        )
        
    # 调用 store 层逻辑同步转正为正式的 slot_value
    val = MemoryProfileStore.upsert_slot_value(
        db=db,
        user_id=current_user.id,
        slot_key=candidate.suggested_slot_key,
        slot_value=final_value,
        confidence=candidate.confidence,
        source="inferred",
        source_session_id=candidate.source_session_id,
        source_message_id=candidate.source_message_id,
        updated_by="assistant"
    )
    
    if not val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该槽位暂不可用或未启用"
        )
        
    # 更新候选偏好状态为 accepted
    candidate.status = "accepted"
    db.commit()
    db.refresh(candidate)
    db.refresh(val)
    
    # 获取关联的 MemorySlot 信息以拼装响应对象
    slot = db.execute(
        select(MemorySlot).where(MemorySlot.id == val.slot_id)
    ).scalar_one()
    
    item = ProfileSlotItem(
        slot_key=slot.slot_key,
        slot_type=slot.slot_type,
        slot_value=val.slot_value,
        confidence=val.confidence,
        source=val.source,
        updated_at=val.updated_at
    )
    return ApiResponse.ok(data=item)


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=ApiResponse[bool],
    summary="拒绝候选偏好",
)
def reject_candidate(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """拒绝候选偏好，将其状态修改为 rejected。"""
    from app.models.memory_profile import MemoryCandidate
    from sqlalchemy import select
    
    candidate = db.execute(
        select(MemoryCandidate)
        .where(MemoryCandidate.id == candidate_id, MemoryCandidate.user_id == current_user.id)
    ).scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该候选偏好记录"
        )
        
    if candidate.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该候选偏好已处理过"
        )
        
    candidate.status = "rejected"
    db.commit()
    return ApiResponse.ok(data=True)

