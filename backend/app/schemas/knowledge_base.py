"""
知识库相关 Schemas
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.knowledge_base import ChunkStrategy


class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., min_length=1, max_length=128, description="知识库名称")
    description: Optional[str] = Field(None, max_length=1000, description="知识库描述")
    chunk_strategy: ChunkStrategy = Field(
        default=ChunkStrategy.RECURSIVE,
        description="分块策略",
    )
    chunk_size: int = Field(default=500, ge=100, le=4000, description="分块大小（字符）")
    chunk_overlap: int = Field(default=50, ge=0, le=1000, description="分块重叠（字符）")
    enable_llm_clean: bool = Field(
        default=False,
        description="是否启用 LLM 文档清洗（可选预处理层，适合格式混乱的 PDF）",
    )


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库请求（全字段可选）"""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=1000)
    chunk_strategy: Optional[ChunkStrategy] = None
    chunk_size: Optional[int] = Field(None, ge=100, le=4000)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=1000)
    enable_llm_clean: Optional[bool] = None


class KnowledgeBaseOut(BaseModel):
    """知识库信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    chunk_strategy: ChunkStrategy
    chunk_size: int
    chunk_overlap: int
    enable_llm_clean: bool = False
    collection_name: Optional[str]
    created_by: int
    created_at: datetime
    updated_at: datetime
    document_count: int = 0  # 包含的文档数（在 service 中填充）
