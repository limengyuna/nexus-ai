"""
Embedding 向量化模块

抽象 BaseEmbedder 接口，提供两个实现：
1. TongyiEmbedder —— 阿里通义 text-embedding-v3 真实 API
2. MockEmbedder   —— 本地确定性 fake 向量（用 hash 生成），用于开发/测试

自动回退逻辑：
- 当 EMBEDDING_PROVIDER=auto 且 DASHSCOPE_API_KEY 未配置时，自动用 Mock。
- 让本地开发流程不依赖外部 API Key。
"""
import hashlib
from abc import ABC, abstractmethod
from typing import List

from loguru import logger

from app.core.config import settings


# ---------- 抽象基类 ----------
class BaseEmbedder(ABC):
    """Embedding 抽象基类"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量将文本转为向量"""
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        """单条文本向量化（query 场景），默认调用 embed_texts"""
        return self.embed_texts([text])[0]


# ---------- 通义 Embedding 实现 ----------
class TongyiEmbedder(BaseEmbedder):
    """
    阿里通义 text-embedding-v3 实现

    官方文档：https://help.aliyun.com/zh/dashscope/developer-reference/text-embedding-api-details
    - 单次最多 10 条文本，每条最多 8192 token
    - 返回 1024 维向量（默认）
    """

    # 通义单次请求的最大文本条数
    MAX_BATCH_SIZE = 10

    def __init__(self, api_key: str, model: str = "text-embedding-v3"):
        if not api_key:
            raise ValueError("TongyiEmbedder 需要有效的 DASHSCOPE_API_KEY")
        # 延迟导入
        import dashscope
        dashscope.api_key = api_key
        self._dashscope = dashscope
        self._model = model
        logger.info("TongyiEmbedder 初始化完成 (model={})", model)

    @property
    def dimension(self) -> int:
        return 1024  # text-embedding-v3 默认维度

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        # 分批调用，规避单批 10 条上限
        for start in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[start:start + self.MAX_BATCH_SIZE]
            resp = self._dashscope.TextEmbedding.call(
                model=self._model,
                input=batch,
            )

            if resp.status_code != 200:
                raise RuntimeError(
                    f"通义 Embedding 调用失败: code={resp.code}, message={resp.message}"
                )

            # resp.output["embeddings"] 是 [{"text_index": 0, "embedding": [...]}, ...]
            embeddings = sorted(
                resp.output["embeddings"],
                key=lambda x: x["text_index"],
            )
            all_embeddings.extend([item["embedding"] for item in embeddings])

        logger.debug("通义向量化完成: {} 条 -> 维度 {}", len(texts), self.dimension)
        return all_embeddings


# ---------- Mock Embedding 实现 ----------
class MockEmbedder(BaseEmbedder):
    """
    本地确定性 Mock Embedder

    用 SHA-256 哈希生成向量，保证：
    - 相同文本产生相同向量（满足"向量库去重/确定性测试"语义）
    - 不依赖任何外部 API，无网络/无 Key 也能跑
    - 维度可配置，与真实 Embedding 对齐
    """

    def __init__(self, dimension: int = 1024):
        self._dimension = dimension
        logger.warning(
            "使用 MockEmbedder（确定性 hash 向量，仅供开发/测试）维度={}",
            dimension,
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_to_vector(text) for text in texts]

    def _hash_to_vector(self, text: str) -> List[float]:
        """
        用 SHA-256 摘要循环填充向量，归一化到 [-1, 1]。
        虽然不是真实语义向量，但是确定性的，可用于验证整个管道。
        """
        vec: List[float] = []
        seed = hashlib.sha256(text.encode("utf-8")).digest()  # 32 bytes
        while len(vec) < self._dimension:
            for byte in seed:
                vec.append((byte - 128) / 128.0)  # [-1, 1)
                if len(vec) >= self._dimension:
                    break
            # 用上一轮结果做新的 hash 输入，增加变化
            seed = hashlib.sha256(seed).digest()
        return vec


# ---------- 工厂函数 ----------
_singleton_embedder: BaseEmbedder | None = None


def get_embedder() -> BaseEmbedder:
    """
    获取 Embedder 单例

    根据配置自动选择 Provider：
    - EMBEDDING_PROVIDER=tongyi → 强制使用通义（无 Key 会抛错）
    - EMBEDDING_PROVIDER=mock   → 强制使用 Mock
    - EMBEDDING_PROVIDER=auto   → 有 Key 用通义，无 Key 用 Mock
    """
    global _singleton_embedder
    if _singleton_embedder is not None:
        return _singleton_embedder

    provider = settings.EMBEDDING_PROVIDER.lower()
    has_key = bool(settings.DASHSCOPE_API_KEY.strip())

    if provider == "tongyi" or (provider == "auto" and has_key):
        _singleton_embedder = TongyiEmbedder(
            api_key=settings.DASHSCOPE_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )
    elif provider == "mock" or (provider == "auto" and not has_key):
        _singleton_embedder = MockEmbedder(dimension=settings.EMBEDDING_DIM)
    else:
        raise ValueError(f"未知的 EMBEDDING_PROVIDER: {provider}")

    return _singleton_embedder


def reset_embedder() -> None:
    """重置单例，主要给测试用"""
    global _singleton_embedder
    _singleton_embedder = None
