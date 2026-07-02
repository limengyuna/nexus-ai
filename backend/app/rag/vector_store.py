"""
向量存储抽象层

抽象 BaseVectorStore 接口，将业务代码与具体向量数据库解耦。
当前提供 ChromaDB HTTP Client 实现，未来切换到 Milvus/Qdrant 仅需新增实现。

ChromaDB Collection 命名约定: "kb_{knowledge_base_id}"
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings

# ---------- BM25 Helper ----------
_STOPWORDS = frozenset(
    "的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 "
    "自己 这 他 她 它 们 那 被 从 把 让 用 但 而 可以 这个 这些 那个 那些 什么 怎么 "
    "如何 为什么 吗 呢 吧 啊 哦 嗯 哈 之 其 或 与 及 等 个 各 为 于 对 中 以 下 里 "
    "面 里面 上面 下面 前 后 左 右 大 小 多 少 来 去 过 做 想 能 会 应该 可能 "
    "请 帮 我们 你们 他们 她们 它们 这里 那里 一下 一些 时候".split()
)

def _tokenize_bm25(text: str) -> List[str]:
    import re
    import jieba
    tokens = []
    for word in jieba.cut(text):
        word = word.strip().lower()
        if not word:
            continue
        if re.fullmatch(r'[\s\W]+', word):
            continue
        if word in _STOPWORDS:
            continue
        if len(word) == 1 and '\u4e00' <= word <= '\u9fa5':
            continue
        tokens.append(word)
    return tokens


# ---------- 检索结果数据结构 ----------
@dataclass
class SearchResult:
    """单条检索结果"""
    chunk_id: str                      # 向量库中分块的唯一 ID
    content: str                       # 分块文本内容
    metadata: Dict[str, Any]           # 关联元数据
    score: float                       # 相似度（距离值越小越相似）


# ---------- 抽象基类 ----------
class BaseVectorStore(ABC):
    """向量存储抽象接口"""

    @abstractmethod
    def ensure_collection(self, collection_name: str) -> None:
        """确保 Collection 存在（不存在则创建）"""
        raise NotImplementedError

    @abstractmethod
    def delete_collection(self, collection_name: str) -> None:
        """删除 Collection"""
        raise NotImplementedError

    @abstractmethod
    def add_chunks(
        self,
        collection_name: str,
        chunk_ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """批量写入分块向量"""
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """向量检索"""
        raise NotImplementedError

    @abstractmethod
    def hybrid_search(
        self,
        collection_name: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        bm25_precomputed: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """双路检索（向量检索 + BM25 关键词检索），并通过 RRF 融合"""
        raise NotImplementedError

    @abstractmethod
    def precompute_bm25(
        self,
        collection_name: str,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """预计算 BM25 索引字典"""
        raise NotImplementedError


    @abstractmethod
    def delete_by_metadata(
        self,
        collection_name: str,
        where: Dict[str, Any],
    ) -> None:
        """按元数据过滤删除（如删除某 document_id 的所有分块）"""
        raise NotImplementedError

    @abstractmethod
    def list_by_metadata(
        self,
        collection_name: str,
        where: Dict[str, Any],
        limit: int = 1000,
        offset: int = 0,
        keyword: Optional[str] = None,
    ) -> List[SearchResult]:
        """按元数据过滤列出所有分块（用于文档预览）"""
        raise NotImplementedError

    @abstractmethod
    def count(self, collection_name: str) -> int:
        """统计 Collection 中向量数量"""
        raise NotImplementedError


# ---------- ChromaDB 实现（双模式：HTTP / 嵌入式）----------
class ChromaVectorStore(BaseVectorStore):
    """
    基于 ChromaDB 的向量存储实现，支持两种运行模式：

    1. **HTTP 模式**（本地 docker-compose 开发用）：连接独立的 chroma 容器
       - 传入 host + port
    2. **嵌入式**（Railway / 单机生产部署用）：Chroma 以库形式在 backend 进程内运行
       - 传入 persist_path，数据存储于该本地目录、无需独立 chroma 服务

    两个参数二选一，persist_path 优先。
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        persist_path: Optional[str] = None,
    ):
        import chromadb

        if persist_path:
            # 嵌入式模式：数据存于本地目录，无独立 chroma 服务
            from pathlib import Path
            Path(persist_path).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=persist_path)
            self._mode = "embedded"
            logger.info("ChromaVectorStore 初始化完成（嵌入式模式，path={}）", persist_path)
        elif host and port:
            # HTTP 模式：连接独立的 Chroma Server（docker-compose 本地开发）
            self._client = chromadb.HttpClient(host=host, port=port)
            self._mode = "http"
            logger.info("ChromaVectorStore 初始化完成（HTTP 模式，host={}, port={}）", host, port)
        else:
            raise ValueError(
                "ChromaVectorStore 初始化失败：必须提供 persist_path 或 (host, port) 二者之一"
            )

    def ensure_collection(self, collection_name: str) -> None:
        # get_or_create_collection 是幂等的
        # 使用 cosine 距离（业界 Embedding 常用度量）
        self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_collection(self, collection_name: str) -> None:
        try:
            self._client.delete_collection(name=collection_name)
            logger.info("已删除 Collection: {}", collection_name)
        except Exception as e:
            # Chroma 在 collection 不存在时会抛 ValueError，忽略即可
            logger.warning("删除 Collection 失败（可能不存在）: {} - {}", collection_name, e)

    def add_chunks(
        self,
        collection_name: str,
        chunk_ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        if not chunk_ids:
            return
        if not (len(chunk_ids) == len(documents) == len(embeddings) == len(metadatas)):
            raise ValueError("chunk_ids/documents/embeddings/metadatas 长度必须一致")

        collection = self._client.get_or_create_collection(name=collection_name)
        # Chroma 自带 upsert 语义，重复 ID 会覆盖
        collection.upsert(
            ids=chunk_ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("向 Collection [{}] 写入 {} 条分块", collection_name, len(chunk_ids))

    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        try:
            collection = self._client.get_collection(name=collection_name)
        except Exception:
            logger.warning("检索时 Collection 不存在: {}", collection_name)
            return []

        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )

        # Chroma 返回格式：每个字段都是 List[List[T]]，外层对应每个 query，内层是 top_k 结果
        ids_list = result.get("ids", [[]])[0]
        docs_list = result.get("documents", [[]])[0]
        meta_list = result.get("metadatas", [[]])[0]
        dist_list = result.get("distances", [[]])[0]

        results = [
            SearchResult(
                chunk_id=chunk_id,
                content=doc or "",
                metadata=meta or {},
                score=float(dist) if dist is not None else 0.0,
            )
            for chunk_id, doc, meta, dist in zip(ids_list, docs_list, meta_list, dist_list)
        ]
        logger.debug("检索 [{}] top_k={} 返回 {} 条", collection_name, top_k, len(results))
        return results

    def hybrid_search(
        self,
        collection_name: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        bm25_precomputed: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        # 1. 密路（密集向量）检索：稍许放大候选集至 top_k * 2
        dense_hits = self.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            top_k=top_k * 2,
            where=where,
        )

        # 2. 疏路（BM25 关键词）检索
        if bm25_precomputed is None:
            bm25_precomputed = self.precompute_bm25(collection_name, where)
            
        all_hits = bm25_precomputed.get("all_hits", [])
        if not all_hits:
            return dense_hits[:top_k]
            
        query_tokens = _tokenize_bm25(query)
        if not query_tokens:
            return dense_hits[:top_k]

        corpus = bm25_precomputed["corpus"]
        idfs = bm25_precomputed["idfs"]
        doc_lens = bm25_precomputed["doc_lens"]
        avg_doc_len = bm25_precomputed["avg_doc_len"]

        # 对每个 Chunk 计算 BM25 得分
        k1 = 1.5
        b = 0.75
        scored_hits = []
        for idx, hit in enumerate(all_hits):
            tf_dict = {}
            for term in corpus[idx]:
                tf_dict[term] = tf_dict.get(term, 0) + 1

            score = 0.0
            doc_len = doc_lens[idx]
            for term in query_tokens:
                if term not in tf_dict:
                    continue
                tf = tf_dict[term]
                idf = idfs.get(term, 0.0)
                term_score = (
                    idf
                    * (tf * (k1 + 1))
                    / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))
                )
                score += term_score

            if score > 0.0:
                scored_hits.append((hit, score))

        # 排序并取前 top_k * 2 个分块作为 BM25 的召回结果
        scored_hits.sort(key=lambda x: x[1], reverse=True)
        sparse_hits = [item[0] for item in scored_hits[: top_k * 2]]

        # 3. RRF (Reciprocal Rank Fusion) 双路合并
        k_rrf = 60
        rrf_scores = {}
        hit_map = {}

        for rank, hit in enumerate(dense_hits, 1):
            rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + 1.0 / (k_rrf + rank)
            hit_map[hit.chunk_id] = hit

        for rank, hit in enumerate(sparse_hits, 1):
            rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + 1.0 / (k_rrf + rank)
            if hit.chunk_id not in hit_map:
                hit_map[hit.chunk_id] = hit

        # 按 RRF 得分降序排序并裁剪出最终的 top_k 个结果
        sorted_chunk_ids = sorted(
            rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True
        )

        # 4. 构造 SearchResult，把 RRF 得分映射为伪距离（0.0 ~ 2.0，越小越相似），契合下游的阈值过滤
        max_possible_rrf = 2.0 / (k_rrf + 1)
        merged_hits = []
        for cid in sorted_chunk_ids[:top_k]:
            original_hit = hit_map[cid]
            rrf_val = rrf_scores[cid]

            # rrf_val 的范围大约在 (1/120) 到 (2/61 ≈ 0.0328)
            # 我们将其线性映射到 0.1 ~ 0.9 的伪距离区间
            pseudo_dist = 0.9 - (rrf_val / max_possible_rrf) * 0.8
            pseudo_dist = max(0.01, min(1.99, pseudo_dist))

            merged_hits.append(
                SearchResult(
                    chunk_id=original_hit.chunk_id,
                    content=original_hit.content,
                    metadata=original_hit.metadata,
                    score=pseudo_dist,
                )
            )

        logger.info(
            "[Hybrid Search] collection={} query={!r} 召回数量 (dense={}, sparse={}) -> 合并输出={}",
            collection_name,
            query,
            len(dense_hits),
            len(sparse_hits),
            len(merged_hits),
        )
        return merged_hits

    def precompute_bm25(
        self,
        collection_name: str,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """预计算 BM25 的 IDF 和 文本分词数据，支持并发预取"""
        all_hits = self.list_by_metadata(
            collection_name=collection_name,
            where=where or {},
            limit=2000,
        )

        if not all_hits:
            return {"all_hits": [], "corpus": [], "idfs": {}, "doc_lens": [], "avg_doc_len": 0.0}

        import math

        corpus = [_tokenize_bm25(h.content) for h in all_hits]
        corpus_size = len(corpus)
        avg_doc_len = sum(len(doc) for doc in corpus) / (corpus_size or 1)
        doc_lens = [len(doc) for doc in corpus]

        doc_freqs = {}
        for doc in corpus:
            for term in set(doc):
                doc_freqs[term] = doc_freqs.get(term, 0) + 1

        idfs = {}
        for term, freq in doc_freqs.items():
            idfs[term] = math.log((corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

        return {
            "all_hits": all_hits,
            "corpus": corpus,
            "idfs": idfs,
            "doc_lens": doc_lens,
            "avg_doc_len": avg_doc_len,
        }


    def delete_by_metadata(
        self,
        collection_name: str,
        where: Dict[str, Any],
    ) -> None:
        try:
            collection = self._client.get_collection(name=collection_name)
        except Exception:
            return
        collection.delete(where=where)
        logger.info("从 Collection [{}] 删除满足条件的分块: {}", collection_name, where)

    def list_by_metadata(
        self,
        collection_name: str,
        where: Dict[str, Any],
        limit: int = 1000,
        offset: int = 0,
        keyword: Optional[str] = None,
    ) -> List[SearchResult]:
        try:
            collection = self._client.get_collection(name=collection_name)
        except Exception:
            return []
        # Chroma 的 collection.get 支持按 where 过滤；不需要 embedding
        get_kwargs = {
            "limit": limit,
            "offset": offset,
            "include": ["documents", "metadatas"],
        }
        if where:
            get_kwargs["where"] = where
        if keyword:
            get_kwargs["where_document"] = {"$contains": keyword}
        raw = collection.get(**get_kwargs)
        ids = raw.get("ids") or []
        docs = raw.get("documents") or []
        metas = raw.get("metadatas") or []
        results: List[SearchResult] = []
        for i in range(len(ids)):
            results.append(
                SearchResult(
                    chunk_id=ids[i],
                    content=docs[i] if i < len(docs) else "",
                    metadata=metas[i] if i < len(metas) else {},
                    score=0.0,  # 非检索结果，无分数
                )
            )
        # 按 chunk_index 排序（如果有），让分块顺序贴近原文
        results.sort(key=lambda r: int(r.metadata.get("chunk_index", 0)) if r.metadata else 0)
        return results

    def count(self, collection_name: str) -> int:
        try:
            collection = self._client.get_collection(name=collection_name)
            return collection.count()
        except Exception:
            return 0


# ---------- 单例工厂 ----------
_singleton_store: BaseVectorStore | None = None


def get_vector_store() -> BaseVectorStore:
    """
    获取 VectorStore 单例。

    根据环境变量决定走 HTTP 模式还是嵌入式：
    - 设置了 CHROMA_PERSIST_PATH → 嵌入式（生产/Railway）
    - 未设置 CHROMA_PERSIST_PATH → HTTP 模式（本地开发，连 docker-compose 中的 chroma 容器）
    """
    global _singleton_store
    if _singleton_store is None:
        if settings.CHROMA_PERSIST_PATH:
            _singleton_store = ChromaVectorStore(
                persist_path=settings.CHROMA_PERSIST_PATH,
            )
        else:
            _singleton_store = ChromaVectorStore(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
            )
    return _singleton_store


def reset_vector_store() -> None:
    """重置单例（测试用）"""
    global _singleton_store
    _singleton_store = None
