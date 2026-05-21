"""
L2 记忆语义检索器

根据当前用户的输入，从 ChromaDB 向量库中语义检索出高度相关的历史记忆事实（Facts），
并通过相关度与重要性的加权重排机制，筛选出 top-k 最有价值的事实，同步更新其实时访问统计。

检索范围策略：
- 当前会话绑定了 kb_id 时：检索 该kb专属记忆 + 全局记忆(kb_id IS NULL)
- 当前会话没有绑定 kb 时：仅检索 全局记忆(kb_id IS NULL)

自动衰减淘汰策略：
- 每个用户每个 kb 维度最多保留 50 条记忆，超出时淘汰综合得分最低的
- 超过 30 天未访问 且 access_count < 2 → 自动降低 importance
- 超过 60 天未访问 且 importance < 0.3 → 自动删除
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.memory import MemoryFact
from app.rag.vector_store import get_vector_store
from app.rag.embedder import get_embedder
from app.memory.store import MemoryStore

# 配置常量
_RELEVANCE_DISTANCE_LIMIT = 0.7   # 余弦距离过滤阈值
_MAX_FACTS_PER_SCOPE = 50         # 每个 user+kb 维度的记忆容量上限
_DECAY_INACTIVE_DAYS = 30         # 未访问多少天后开始衰减 importance
_PURGE_INACTIVE_DAYS = 60         # 未访问多少天且 importance < 0.3 时自动删除
_CST = timezone(timedelta(hours=8))


class MemoryRetriever:
    """L2 记忆事实检索器"""

    @staticmethod
    def retrieve(
        db: Session,
        user_input: str,
        user_id: int,
        kb_id: Optional[int] = None,
        top_k: int = 3
    ) -> List[MemoryFact]:
        """
        检索与当前用户输入高度相关的记忆事实（按 kb_id 范围过滤）

        :param db: 数据库 Session
        :param user_input: 当前用户输入
        :param user_id: 用户 ID
        :param kb_id: 当前会话关联的知识库 ID（None 表示仅检索全局记忆）
        :param top_k: 获取排名前 K 的记忆
        :return: 关联的 MemoryFact 数据库对象列表
        """
        collection_name = MemoryStore.get_collection_name(user_id)
        vector_store = get_vector_store()
        embedder = get_embedder()

        # 如果用户的向量 Collection 不存在，说明无记忆事实，直接返回空
        if vector_store.count(collection_name) == 0:
            return []

        # 1. 向量化用户输入
        query_embedding = embedder.embed_query(user_input)

        # 2. 从向量库中召回候选记忆 (取 top_k * 3 个候选进行后续过滤和重排)
        candidate_hits = vector_store.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            top_k=top_k * 3
        )

        if not candidate_hits:
            return []

        # 3. 关联度过滤 + kb_id 范围过滤 + 加权重排
        scored_candidates: List[Tuple[MemoryFact, float]] = []

        for hit in candidate_hits:
            if hit.score > _RELEVANCE_DISTANCE_LIMIT:
                continue

            try:
                fact_id = int(hit.chunk_id.replace("mem_", ""))
                fact = db.get(MemoryFact, fact_id)
                if not fact or fact.user_id != user_id:
                    continue

                # 所有记忆统一为全局可见，靠语义相似度自然过滤相关性

                cosine_similarity = 1.0 - hit.score
                # 综合得分 = 0.7 * 余弦相似度 + 0.3 * 重要性
                final_score = 0.7 * cosine_similarity + 0.3 * fact.importance

                scored_candidates.append((fact, final_score))
            except Exception as e:
                logger.warning("[Memory Retriever] 候选事实加载或打分出错: {}", e)

        # 按综合得分从大到小排序，裁剪出 top_k
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        selected_pairs = scored_candidates[:top_k]

        if not selected_pairs:
            return []

        # 4. 更新已被采用的记忆的使用统计
        selected_facts = []
        now_time = datetime.now(_CST)

        for fact, score in selected_pairs:
            try:
                fact.access_count += 1
                fact.last_accessed_at = now_time
                selected_facts.append(fact)
            except Exception as e:
                logger.warning("[Memory Retriever] 更新记忆访问统计出错: {}", e)

        try:
            db.commit()
            logger.info(
                "[Memory Retriever] 为用户 {} (kb={}) 检索到 {} 条相关记忆事实",
                user_id, kb_id, len(selected_facts)
            )
        except Exception as e:
            logger.warning("[Memory Retriever] 提交记忆访问更新事务失败: {}", e)

        # 5. 后台触发轻量衰减淘汰（不阻塞检索返回）
        try:
            MemoryRetriever._run_decay_and_prune(db, user_id, kb_id)
        except Exception as e:
            logger.warning("[Memory Retriever] 衰减淘汰执行出错（不影响检索结果）: {}", e)

        return selected_facts

    @staticmethod
    def _run_decay_and_prune(db: Session, user_id: int, kb_id: Optional[int] = None) -> None:
        """
        轻量级衰减淘汰机制，在每次检索后执行：
        1. 时间衰减：长期未访问的记忆降低 importance
        2. 自动删除：极低价值的过期记忆直接删除
        3. 容量淘汰：超过上限时删除综合得分最低的记忆
        """
        now_time = datetime.now(_CST)
        decay_cutoff = now_time - timedelta(days=_DECAY_INACTIVE_DAYS)
        purge_cutoff = now_time - timedelta(days=_PURGE_INACTIVE_DAYS)

        # --- 阶段 1：自动删除超过 60 天未访问且 importance < 0.3 的记忆 ---
        # 不再有 access_count 豁免，所有过期低价值记忆均可被清除
        purge_candidates = (
            db.query(MemoryFact)
            .filter(
                MemoryFact.user_id == user_id,
                or_(
                    # 从未被访问过且创建超过 60 天
                    and_(
                        MemoryFact.last_accessed_at.is_(None),
                        MemoryFact.created_at < purge_cutoff,
                    ),
                    # 最后访问超过 60 天
                    MemoryFact.last_accessed_at < purge_cutoff,
                ),
                MemoryFact.importance < 0.3,
            )
            .all()
        )

        if purge_candidates:
            for fact in purge_candidates:
                MemoryStore.delete_fact(db, fact.id)
            logger.info("[Memory Decay] 自动清除 {} 条过期低价值记忆 (user_id={})", len(purge_candidates), user_id)

        # --- 阶段 2：时间衰减，超过 30 天未访问的记忆降低 importance ---
        # 衰减幅度根据 access_count 动态调节：引用越多衰减越慢，但不豁免
        decay_candidates = (
            db.query(MemoryFact)
            .filter(
                MemoryFact.user_id == user_id,
                or_(
                    and_(
                        MemoryFact.last_accessed_at.is_(None),
                        MemoryFact.created_at < decay_cutoff,
                    ),
                    MemoryFact.last_accessed_at < decay_cutoff,
                ),
                MemoryFact.importance >= 0.3,  # 还没低到可以直接删的
            )
            .all()
        )

        if decay_candidates:
            for fact in decay_candidates:
                # 根据 access_count 动态确定衰减幅度
                # 引用越多 → 衰减越慢，但所有记忆都会衰减（无豁免）
                if fact.access_count == 0:
                    decay_amount = 0.15   # 从未被引用，衰减快
                elif fact.access_count <= 3:
                    decay_amount = 0.10   # 少量引用，正常衰减
                elif fact.access_count <= 9:
                    decay_amount = 0.05   # 中频引用，衰减慢
                else:
                    decay_amount = 0.02   # 高频引用，衰减极慢但仍会衰减
                fact.importance = max(0.1, fact.importance - decay_amount)
            db.commit()
            logger.info("[Memory Decay] 对 {} 条长期未访问记忆执行 importance 衰减 (user_id={})", len(decay_candidates), user_id)

        # --- 阶段 3：容量淘汰（分 kb 维度）---
        # 分别检查全局记忆和当前 kb 记忆的容量
        scopes_to_check = [None]  # 全局记忆
        if kb_id is not None:
            scopes_to_check.append(kb_id)

        for scope_kb_id in scopes_to_check:
            if scope_kb_id is None:
                scope_query = db.query(MemoryFact).filter(
                    MemoryFact.user_id == user_id,
                    MemoryFact.kb_id.is_(None),
                )
            else:
                scope_query = db.query(MemoryFact).filter(
                    MemoryFact.user_id == user_id,
                    MemoryFact.kb_id == scope_kb_id,
                )

            total_count = scope_query.count()
            if total_count <= _MAX_FACTS_PER_SCOPE:
                continue

            # 超出容量，按 importance 升序 + access_count 升序 排列，淘汰最不重要的
            overflow = total_count - _MAX_FACTS_PER_SCOPE
            to_evict = (
                scope_query
                .order_by(MemoryFact.importance.asc(), MemoryFact.access_count.asc())
                .limit(overflow)
                .all()
            )
            for fact in to_evict:
                MemoryStore.delete_fact(db, fact.id)
            logger.info(
                "[Memory Decay] 容量淘汰 {} 条记忆 (user_id={}, kb_id={}，上限={})",
                len(to_evict), user_id, scope_kb_id, _MAX_FACTS_PER_SCOPE
            )
