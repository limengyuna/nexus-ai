"""
文档 API 路由

提供文档上传、列表查询、删除、检索（测试用）等接口。
"""
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.rag.embedder import get_embedder
from app.rag.vector_store import get_vector_store
from app.schemas.common import ApiResponse
from app.schemas.document import (
    ChunkPreview,
    ChunksResponse,
    DocumentOut,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.schemas.task import TaskRecordOut
from app.services.document_service import DocumentService
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-bases/{kb_id}", tags=["文档"])


@router.post(
    "/documents",
    response_model=ApiResponse[dict],
    summary="上传文档（异步处理）",
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(
    kb_id: int,
    file: UploadFile = File(..., description="待上传的文档文件"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传文档后立即返回 document_id + task_id；
    实际解析/分块/向量化由 Celery Worker 异步执行。
    前端通过 GET /tasks/{task_id} 轮询进度。
    """
    kb = KnowledgeBaseService.get(db, kb_id, user_id=current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    try:
        document, task_record = DocumentService.upload(db, kb, file)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return ApiResponse.ok(
        data={
            "document": DocumentOut.model_validate(document).model_dump(mode="json"),
            "task": TaskRecordOut.model_validate(task_record).model_dump(mode="json"),
        },
        message="上传成功，文档正在后台处理",
    )


@router.get(
    "/documents",
    response_model=ApiResponse[List[DocumentOut]],
    summary="列出知识库下的全部文档",
)
def list_documents(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if KnowledgeBaseService.get(db, kb_id, user_id=current_user.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    docs = DocumentService.list_by_kb(db, kb_id)
    return ApiResponse.ok(data=[DocumentOut.model_validate(d) for d in docs])


@router.delete(
    "/documents/{document_id}",
    response_model=ApiResponse[None],
    summary="删除文档（同步清理向量库分块与物理文件）",
)
def delete_document(
    kb_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 多租户隔离：先验证 kb 归属
    if KnowledgeBaseService.get(db, kb_id, user_id=current_user.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    doc = DocumentService.get(db, document_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    DocumentService.delete(db, doc)
    return ApiResponse.ok(message="文档已删除")


@router.get(
    "/documents/{document_id}/chunks",
    response_model=ApiResponse[ChunksResponse],
    summary="查看文档的所有分块（用于预览切分效果）",
)
def list_document_chunks(
    kb_id: int,
    document_id: int,
    limit: int = 1000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    返回某文档解析后产出的所有 chunks，按 chunk_index 顺序。
    用途：让用户在 UI 上"看见"分块策略的真实效果。
    """
    # 多租户隔离：先验证 kb 是当前用户的
    kb = KnowledgeBaseService.get(db, kb_id, user_id=current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if not kb.collection_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="知识库未初始化向量集合")
    doc = DocumentService.get(db, document_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    vector_store = get_vector_store()
    raw_chunks = vector_store.list_by_metadata(
        collection_name=kb.collection_name,
        where={"document_id": document_id},
        limit=limit,
    )

    return ApiResponse.ok(
        data=ChunksResponse(
            document_id=document_id,
            file_name=doc.file_name,
            total=len(raw_chunks),
            chunks=[
                ChunkPreview(chunk_id=c.chunk_id, content=c.content, metadata=c.metadata)
                for c in raw_chunks
            ],
        )
    )


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=ApiResponse[TaskRecordOut],
    status_code=status.HTTP_202_ACCEPTED,
    summary="重新处理文档（清理旧向量 + 重新投递 Celery 任务）",
)
def reprocess_document(
    kb_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    适用场景：
    - 文档上次处理失败，想重试
    - 知识库切分策略改了，想重切已有文档
    """
    # 多租户隔离：先验证 kb 归属
    if KnowledgeBaseService.get(db, kb_id, user_id=current_user.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    doc = DocumentService.get(db, document_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    task_record = DocumentService.reprocess(db, doc)
    return ApiResponse.ok(
        data=TaskRecordOut.model_validate(task_record),
        message="文档已重新投递处理",
    )


@router.post(
    "/search",
    response_model=ApiResponse[SearchResponse],
    summary="RAG 检索（仅供阶段二测试，正式对话由 Agent 触发）",
)
def search_knowledge_base(
    kb_id: int,
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    在指定知识库中按 query 进行向量检索，返回 top_k 最相似分块。

    这个接口用于：
    - 阶段二验证 RAG 管道是否真的能召回相关文档
    - 阶段三 RAG Agent 节点直接复用此逻辑
    """
    kb = KnowledgeBaseService.get(db, kb_id, user_id=current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if not kb.collection_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="知识库尚未初始化向量集合",
        )

    embedder = get_embedder()
    query_vec = embedder.embed_query(payload.query)

    vector_store = get_vector_store()
    raw_hits = vector_store.search(
        collection_name=kb.collection_name,
        query_embedding=query_vec,
        top_k=payload.top_k,
    )

    hits = [
        SearchHit(
            chunk_id=h.chunk_id,
            content=h.content,
            metadata=h.metadata,
            score=h.score,
        )
        for h in raw_hits
    ]
    return ApiResponse.ok(
        data=SearchResponse(query=payload.query, hits=hits)
    )
