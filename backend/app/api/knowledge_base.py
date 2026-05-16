"""
知识库 API 路由

提供 KB 的 CRUD 接口，所有接口需要登录。
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-bases", tags=["知识库"])


@router.post(
    "",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="创建知识库",
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建一个新的知识库，并在向量库中初始化对应 Collection。"""
    try:
        kb = KnowledgeBaseService.create(db, payload, owner_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    out = KnowledgeBaseOut.model_validate(kb)
    out.document_count = 0
    return ApiResponse.ok(data=out, message="知识库创建成功")


@router.get(
    "",
    response_model=ApiResponse[List[KnowledgeBaseOut]],
    summary="列出全部知识库",
)
def list_knowledge_bases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户创建的知识库（含文档数量）。多租户隔离。"""
    items = KnowledgeBaseService.list_with_doc_count(db, user_id=current_user.id)
    result = []
    for kb, doc_count in items:
        out = KnowledgeBaseOut.model_validate(kb)
        out.document_count = doc_count
        result.append(out)
    return ApiResponse.ok(data=result)


@router.get(
    "/{kb_id}",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="获取知识库详情",
)
def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = KnowledgeBaseService.get(db, kb_id, user_id=current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    out = KnowledgeBaseOut.model_validate(kb)
    out.document_count = KnowledgeBaseService.count_documents(db, kb_id)
    return ApiResponse.ok(data=out)


@router.patch(
    "/{kb_id}",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="更新知识库",
)
def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = KnowledgeBaseService.get(db, kb_id, user_id=current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    try:
        kb = KnowledgeBaseService.update(db, kb, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    out = KnowledgeBaseOut.model_validate(kb)
    out.document_count = KnowledgeBaseService.count_documents(db, kb_id)
    return ApiResponse.ok(data=out, message="更新成功")


@router.delete(
    "/{kb_id}",
    response_model=ApiResponse[None],
    summary="删除知识库（同步清理向量库）",
)
def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = KnowledgeBaseService.get(db, kb_id, user_id=current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    KnowledgeBaseService.delete(db, kb)
    return ApiResponse.ok(message="知识库已删除")
