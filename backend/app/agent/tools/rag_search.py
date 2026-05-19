"""
RAG 检索工具

把"在指定知识库里向量检索"封装成 Tool，便于 Skill 编排时复用。
和 RAG Agent 不同的是：这里只做"检索"这一步，不做"生成回答"。
"""
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from app.agent.tools.registry import BaseTool, register_tool
from app.core.database import SessionLocal
from app.models.knowledge_base import KnowledgeBase
from app.rag.embedder import get_embedder
from app.rag.vector_store import get_vector_store


class RAGSearchArgs(BaseModel):
    """RAG 检索参数"""
    kb_id: int = Field(..., description="知识库 ID")
    query: str = Field(..., description="检索查询")
    top_k: int = Field(default=5, ge=1, le=20, description="返回的相关分块数量")


@register_tool
class RAGSearchTool(BaseTool):
    """
    在指定知识库中做向量检索，返回 top_k 个相关分块。

    典型用法（在 Skill 内调用）:
        chunks = self._call_tool("rag_search", kb_id=1, query="什么是 LangGraph", top_k=5)
    """
    name = "rag_search"
    description = (
        "在指定知识库中按语义相似度检索 top_k 个最相关的文档分块。"
        "不生成回答，只返回原始分块。适用于：摘要、问答、信息抽取等需要先拿原始证据的场景。"
    )
    args_schema = RAGSearchArgs

    def run(self, **kwargs) -> List[Dict[str, Any]]:
        params = RAGSearchArgs(**kwargs)

        # 1. 查 KB（用独立 Session，避免 Skill 上下文里的 db 污染）
        db = SessionLocal()
        try:
            kb: Optional[KnowledgeBase] = db.get(KnowledgeBase, params.kb_id)
            if kb is None:
                raise ValueError(f"知识库不存在: {params.kb_id}")
            if not kb.collection_name:
                raise ValueError(f"知识库 {params.kb_id} 尚未初始化向量集合")
            collection_name = kb.collection_name
        finally:
            db.close()

        # 2. 向量化 + 检索
        embedder = get_embedder()
        query_vec = embedder.embed_query(params.query)

        vector_store = get_vector_store()
        raw_hits = vector_store.hybrid_search(
            collection_name=collection_name,
            query=params.query,
            query_embedding=query_vec,
            top_k=params.top_k,
        )

        results = [
            {
                "chunk_id": h.chunk_id,
                "content": h.content,
                "metadata": h.metadata,
                "score": h.score,
            }
            for h in raw_hits
        ]
        logger.debug("[rag_search] kb={} query={!r} top_k={} -> {} 条",
                     params.kb_id, params.query, params.top_k, len(results))
        return results
