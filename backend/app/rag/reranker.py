"""
重排模型（Reranker）

职责：对粗召回的候选 chunk 进行精排，提升相关度排序质量。

架构：
1. 粗召回（向量检索 + BM25 混合）返回 top_k 个候选
2. Reranker 对候选做交叉编码，根据 query-document 对的相关性重新排序
3. 取重排后的 top_n 送给 LLM 生成回答

实现：
- TongyiReranker：使用 DashScope 的 gte-rerank 模型
- MockReranker：开发/测试用，保持原始顺序不变
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from loguru import logger

from app.core.config import settings


@dataclass
class RerankResult:
    """重排结果"""
    index: int           # 原始列表中的索引
    relevance_score: float  # 相关性分数（越大越相关）


# ---------- 抽象基类 ----------
class BaseReranker(ABC):
    """重排模型抽象基类"""

    @abstractmethod
    def rerank(self, query: str, documents: List[str], top_n: int = 5) -> List[RerankResult]:
        """
        对文档列表按与 query 的相关性重排

        :param query: 用户查询
        :param documents: 候选文档列表
        :param top_n: 返回前 N 个结果
        :return: 按相关性降序排列的结果列表
        """
        raise NotImplementedError


# ---------- 通义 Reranker 实现 ----------
class TongyiReranker(BaseReranker):
    """
    基于 DashScope gte-rerank 的重排模型

    官方文档：https://help.aliyun.com/zh/dashscope/developer-reference/api-details-rerank
    - 单次最多 500 篇文档
    - 支持中英文
    """

    def __init__(self, api_key: str, model: str = "gte-rerank"):
        if not api_key:
            raise ValueError("TongyiReranker 需要有效的 DASHSCOPE_API_KEY")
        import dashscope
        dashscope.api_key = api_key
        self._model = model
        logger.info("TongyiReranker 初始化完成 (model={})", model)

    def rerank(self, query: str, documents: List[str], top_n: int = 5) -> List[RerankResult]:
        if not documents:
            return []

        import dashscope

        resp = dashscope.TextReRank.call(
            model=self._model,
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"通义 Rerank 调用失败: code={resp.code}, message={resp.message}"
            )

        results = []
        for item in resp.output.get("results", []):
            results.append(RerankResult(
                index=item["index"],
                relevance_score=item["relevance_score"],
            ))

        # 按相关性分数降序排序
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        logger.debug(
            "TongyiReranker 重排完成: query={!r} 输入={} 篇 -> 输出={} 篇, top_score={:.4f}",
            query[:30], len(documents), len(results),
            results[0].relevance_score if results else 0,
        )
        return results


# ---------- Mock Reranker 实现 ----------
class MockReranker(BaseReranker):
    """
    开发/测试用 Mock 重排器

    保持原始顺序不变，分数按位置递减。
    """

    def __init__(self):
        logger.warning("使用 MockReranker（保持原始顺序，仅供开发/测试）")

    def rerank(self, query: str, documents: List[str], top_n: int = 5) -> List[RerankResult]:
        results = [
            RerankResult(index=i, relevance_score=1.0 - i * 0.1)
            for i in range(min(top_n, len(documents)))
        ]
        return results


# ---------- 工厂函数 ----------
_singleton_reranker: BaseReranker | None = None


def get_reranker() -> BaseReranker:
    """
    获取 Reranker 单例

    复用 DASHSCOPE_API_KEY 配置：
    - 有 Key → 使用通义 gte-rerank
    - 无 Key → 使用 Mock
    """
    global _singleton_reranker
    if _singleton_reranker is not None:
        return _singleton_reranker

    has_key = bool(settings.DASHSCOPE_API_KEY.strip())

    if has_key:
        _singleton_reranker = TongyiReranker(
            api_key=settings.DASHSCOPE_API_KEY,
            model=settings.RERANK_MODEL,
        )
    else:
        _singleton_reranker = MockReranker()

    return _singleton_reranker
