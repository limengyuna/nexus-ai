"""
知识库业务逻辑层

封装 KB 的 CRUD，及"删除 KB 时同步清理向量库 Collection"等组合操作。
"""
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.rag.vector_store import get_vector_store
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate


class KnowledgeBaseService:
    """知识库相关业务方法集合"""

    @staticmethod
    def _build_collection_name(kb_id: int) -> str:
        """统一 Collection 命名规则"""
        return f"kb_{kb_id}"

    # ---------- CRUD ----------
    @staticmethod
    def create(db: Session, payload: KnowledgeBaseCreate, owner_id: int) -> KnowledgeBase:
        """创建知识库，同时在向量库中初始化 Collection"""
        if payload.chunk_overlap >= payload.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")

        kb = KnowledgeBase(
            name=payload.name,
            description=payload.description,
            chunk_strategy=payload.chunk_strategy,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
            enable_llm_clean=payload.enable_llm_clean,
            created_by=owner_id,
        )
        db.add(kb)
        db.flush()  # 拿到 kb.id

        # 用 id 生成 collection 名并回写
        kb.collection_name = KnowledgeBaseService._build_collection_name(kb.id)
        db.commit()
        db.refresh(kb)

        # 同步在向量库中创建 Collection（幂等）
        try:
            get_vector_store().ensure_collection(kb.collection_name)
        except Exception as e:
            # 向量库失败不应阻断 KB 创建，仅记录告警
            logger.warning("创建向量 Collection 失败（稍后可重试）: {}", e)

        return kb

    @staticmethod
    def get(db: Session, kb_id: int, user_id: Optional[int] = None) -> Optional[KnowledgeBase]:
        """
        按 ID 取知识库。
        若传 user_id，会校验 created_by==user_id（多租户隔离）。
        """
        kb = db.get(KnowledgeBase, kb_id)
        if kb is None:
            return None
        if user_id is not None and kb.created_by != user_id:
            return None  # 不是自己的 KB，统一当成 "不存在" 防止枚举
        return kb

    @staticmethod
    def list_with_doc_count(
        db: Session,
        user_id: Optional[int] = None,
    ) -> List[Tuple[KnowledgeBase, int]]:
        """
        列出知识库 + 每个的文档数量（一次性 join 查询）。
        若传 user_id，只列出该用户创建的（多租户隔离）。
        """
        stmt = (
            select(KnowledgeBase, func.count(Document.id))
            .outerjoin(Document, Document.kb_id == KnowledgeBase.id)
            .group_by(KnowledgeBase.id)
            .order_by(KnowledgeBase.created_at.desc())
        )
        if user_id is not None:
            stmt = stmt.where(KnowledgeBase.created_by == user_id)
        return [(kb, count) for kb, count in db.execute(stmt).all()]

    @staticmethod
    def update(
        db: Session,
        kb: KnowledgeBase,
        payload: KnowledgeBaseUpdate,
    ) -> KnowledgeBase:
        update_data = payload.model_dump(exclude_unset=True)
        # 校验 overlap/size 关系
        new_size = update_data.get("chunk_size", kb.chunk_size)
        new_overlap = update_data.get("chunk_overlap", kb.chunk_overlap)
        if new_overlap >= new_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")

        for k, v in update_data.items():
            setattr(kb, k, v)
        db.commit()
        db.refresh(kb)
        return kb

    @staticmethod
    def delete(db: Session, kb: KnowledgeBase) -> None:
        """删除知识库，同步清理向量库 Collection"""
        collection_name = kb.collection_name
        db.delete(kb)
        db.commit()

        if collection_name:
            try:
                get_vector_store().delete_collection(collection_name)
            except Exception as e:
                logger.warning("删除向量 Collection 失败: {}", e)

    @staticmethod
    def count_documents(db: Session, kb_id: int) -> int:
        """统计某知识库下的文档数"""
        stmt = select(func.count(Document.id)).where(Document.kb_id == kb_id)
        return db.scalar(stmt) or 0
