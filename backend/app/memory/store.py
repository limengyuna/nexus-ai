"""
L2 记忆事实持久化与 ChromaDB 存储管理器

负责将 LLM 抽取的记忆事实写入 PostgreSQL (元数据) 和 ChromaDB (向量索引)，
并包含相似度去重逻辑。
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy.orm import Session

from app.models.memory import MemoryFact, MemoryFactType
from app.rag.vector_store import get_vector_store
from app.rag.embedder import get_embedder


class MemoryStore:
    """L2 记忆事实存储管理器"""

    @staticmethod
    def get_collection_name(user_id: int) -> str:
        """根据用户 ID 获取对应的 ChromaDB Collection 名称"""
        return f"memory_user_{user_id}"

    @classmethod
    def save_fact(
        cls,
        db: Session,
        user_id: int,
        content: str,
        fact_type: str,
        importance: float,
        session_id: Optional[int] = None,
        kb_id: Optional[int] = None
    ) -> MemoryFact:
        """
        保存单条记忆事实。
        包含高级的语义去重逻辑：如果已存在相似度极高的事实，则更新并增加其访问计数，不重复创建。

        :param db: 数据库 Session
        :param user_id: 用户 ID
        :param content: 事实文本内容
        :param fact_type: 事实类型 (MemoryFactType)
        :param importance: 重要性 (0.0 ~ 1.0)
        :param session_id: 来源会话 ID
        :param kb_id: 关联知识库 ID（NULL 为全局记忆，如用户偏好）
        :return: 保存或更新后的 MemoryFact 对象
        """
        collection_name = cls.get_collection_name(user_id)
        vector_store = get_vector_store()
        embedder = get_embedder()

        # 确保用户的 Collection 存在
        vector_store.ensure_collection(collection_name)

        # 1. 计算新事实的向量
        query_embedding = embedder.embed_query(content)

        # 2. 检索 ChromaDB 中最相似的现有事实 (Top-1)
        # 这里的 score 是余弦距离，距离越小越相似（0.0 表示完全相同，2.0 表示完全相反）
        existing_hits = vector_store.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            top_k=1
        )

        # 语义重复检测阈值：余弦距离小于 0.15 (即相似度 > 0.85) 则视为同一条记忆
        SIMILARITY_THRESHOLD = 0.15

        if existing_hits and existing_hits[0].score < SIMILARITY_THRESHOLD:
            hit = existing_hits[0]
            # 获取对应的 PostgreSQL 实体 ID
            try:
                fact_id = int(hit.chunk_id.replace("mem_", ""))
                fact = db.get(MemoryFact, fact_id)
                if fact and fact.user_id == user_id:
                    logger.info(
                        "[Memory Store] 检测到语义重复的事实 (现有距离={:.4f})，执行合并更新。\n新: {}\n旧: {}",
                        hit.score, content, fact.content
                    )
                    # 语义命中即视为同一事实的更新，无条件采用最新表述
                    # 理由：避免 "Python 3.9 → 3.12" 等长度相近但信息过期时不触发更新
                    fact.content = content
                    fact.importance = max(fact.importance, importance)
                    # 同步更新向量库中的文本
                    vector_store.add_chunks(
                        collection_name=collection_name,
                        chunk_ids=[hit.chunk_id],
                        documents=[content],
                        embeddings=[query_embedding],
                        metadatas=[hit.metadata]
                    )
                    
                    # 增加访问权重和最后访问时间
                    fact.access_count += 1
                    _CST = timezone(timedelta(hours=8))
                    fact.last_accessed_at = datetime.now(_CST)
                    db.commit()
                    db.refresh(fact)
                    return fact
            except Exception as e:
                logger.warning("[Memory Store] 语义去重后续处理出错，将降级为直接创建: {}", e)

        # 3. 语义不重复，创建全新 MemoryFact
        fact = MemoryFact(
            user_id=user_id,
            session_id=session_id,
            kb_id=kb_id,
            fact_type=MemoryFactType(fact_type),
            content=content,
            importance=importance,
            access_count=0
        )
        db.add(fact)
        db.commit()
        db.refresh(fact)

        # 4. 同步写入 ChromaDB
        chunk_id = f"mem_{fact.id}"
        metadata = {
            "fact_id": fact.id,
            "user_id": user_id,
            "kb_id": kb_id if kb_id is not None else -1,  # ChromaDB metadata 不支持 None
            "fact_type": fact.fact_type.value,
            "importance": fact.importance
        }
        vector_store.add_chunks(
            collection_name=collection_name,
            chunk_ids=[chunk_id],
            documents=[content],
            embeddings=[query_embedding],
            metadatas=[metadata]
        )

        logger.info("[Memory Store] 成功创建并向量化新记忆事实 (ID: {}, 类型: {})", fact.id, fact_type)
        return fact

    @classmethod
    def delete_fact(cls, db: Session, fact_id: int) -> bool:
        """
        删除记忆事实（PostgreSQL + ChromaDB 同步删除）

        :param db: 数据库 Session
        :param fact_id: 事实 ID
        :return: 是否删除成功
        """
        fact = db.get(MemoryFact, fact_id)
        if not fact:
            return False

        user_id = fact.user_id
        collection_name = cls.get_collection_name(user_id)
        vector_store = get_vector_store()

        # 1. 从 ChromaDB 删除
        chunk_id = f"mem_{fact_id}"
        vector_store.delete_by_metadata(
            collection_name=collection_name,
            where={"fact_id": fact_id}
        )

        # 2. 从 PostgreSQL 删除
        db.delete(fact)
        db.commit()
        logger.info("[Memory Store] 同步删除记忆事实 (ID: {})", fact_id)
        return True
