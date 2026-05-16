"""
文档相关 Schemas
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class DocumentOut(BaseModel):
    """文档信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    file_name: str
    file_type: str
    file_size: int
    chunk_count: int
    status: DocumentStatus
    error_msg: Optional[str]
    created_at: datetime
    updated_at: datetime


class SearchRequest(BaseModel):
    """RAG 检索请求（仅用于测试，正式对话由 Agent 调用）"""
    query: str
    top_k: int = 5


class SearchHit(BaseModel):
    """单条检索结果"""
    chunk_id: str
    content: str
    metadata: dict
    score: float


class SearchResponse(BaseModel):
    """检索响应"""
    query: str
    hits: list[SearchHit]


class ChunkPreview(BaseModel):
    """单个文档分块预览"""
    chunk_id: str
    content: str
    metadata: dict


class ChunksResponse(BaseModel):
    """文档分块预览响应"""
    document_id: int
    file_name: str
    total: int
    chunks: list[ChunkPreview]
