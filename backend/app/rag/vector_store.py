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
    ) -> List[SearchResult]:
        """按元数据过滤列出所有分块（用于文档预览）"""
        raise NotImplementedError

    @abstractmethod
    def count(self, collection_name: str) -> int:
        """统计 Collection 中向量数量"""
        raise NotImplementedError


# ---------- ChromaDB HTTP 实现 ----------
class ChromaVectorStore(BaseVectorStore):
    """
    基于 ChromaDB HTTP Client 的实现

    连接到 docker 中运行的 chroma server，避免 Windows 上原生编译问题。
    """

    def __init__(self, host: str, port: int):
        import chromadb

        # HttpClient 直接连远程 Chroma Server，不需要本地 hnswlib
        self._client = chromadb.HttpClient(host=host, port=port)
        logger.info("ChromaVectorStore 初始化完成 (host={}, port={})", host, port)

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
    ) -> List[SearchResult]:
        try:
            collection = self._client.get_collection(name=collection_name)
        except Exception:
            return []
        # Chroma 的 collection.get 支持按 where 过滤；不需要 embedding
        raw = collection.get(where=where, limit=limit, include=["documents", "metadatas"])
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
    """获取 VectorStore 单例"""
    global _singleton_store
    if _singleton_store is None:
        _singleton_store = ChromaVectorStore(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
        )
    return _singleton_store


def reset_vector_store() -> None:
    """重置单例（测试用）"""
    global _singleton_store
    _singleton_store = None
