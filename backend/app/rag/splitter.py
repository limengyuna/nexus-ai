"""
文本分块策略（策略模式）

提供两种切分策略：
1. RecursiveSplitter      —— 通用递归字符分块，适合任意文本
2. MarkdownHeaderSplitter —— 按 Markdown 标题层级分块，保留语义结构

设计：
- 抽象基类 BaseSplitter 规定 .split() 接口
- 工厂函数 get_splitter() 根据策略名 + 参数返回具体实例
- 上层（KB Service）按知识库配置选择策略，业务代码无需感知实现差异
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List

from loguru import logger

from app.models.knowledge_base import ChunkStrategy


@dataclass
class Chunk:
    """文本分块的统一数据结构"""
    content: str                                  # 分块文本内容
    metadata: Dict[str, str | int] = field(default_factory=dict)  # 元数据（如所属标题、序号等）


# ---------- 抽象基类 ----------
class BaseSplitter(ABC):
    """分块策略基类"""

    @abstractmethod
    def split(self, text: str) -> List[Chunk]:
        """将文本切分为多个 Chunk"""
        raise NotImplementedError


# ---------- 具体策略：通用递归分块 ----------
class RecursiveSplitter(BaseSplitter):
    """
    通用递归字符分块器

    包装 langchain-text-splitters 的 RecursiveCharacterTextSplitter，
    它会按 ["\\n\\n", "\\n", " ", ""] 的优先级递归切分，
    最大程度保留语义边界。
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")

        # 延迟导入，加快冷启动
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            # 中文文档的优先分隔符（"\n\n" > "\n" > "。" > "！？" > " " > ""）
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> List[Chunk]:
        raw_chunks = self._splitter.split_text(text)
        chunks = [
            Chunk(
                content=chunk_text,
                metadata={"chunk_index": idx, "strategy": "recursive"},
            )
            for idx, chunk_text in enumerate(raw_chunks)
        ]
        logger.info(
            "RecursiveSplitter 切分完成: {} 字符 -> {} 块 (size={}, overlap={})",
            len(text), len(chunks), self.chunk_size, self.chunk_overlap,
        )
        return chunks


# ---------- 具体策略：Markdown 标题分块 ----------
class MarkdownHeaderSplitter(BaseSplitter):
    """
    Markdown 标题层级分块器

    先按一级到三级标题切分以保留文档结构，
    再用 RecursiveSplitter 对超长块二次切分，保证每块不超过 chunk_size。

    每个 Chunk 的 metadata 会包含完整标题路径（如 "第一章 > 1.1 节"），
    便于检索时返回上下文。
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 80):
        from langchain_text_splitters import (
            MarkdownHeaderTextSplitter,
            RecursiveCharacterTextSplitter,
        )

        # 一二三级标题都作为切分依据
        headers_to_split_on = [
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
        ]
        self._md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False,  # 保留标题文本在分块内容里，提升检索可读性
        )
        self._sub_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> List[Chunk]:
        # 第一阶段：按标题切分
        md_docs = self._md_splitter.split_text(text)

        chunks: List[Chunk] = []
        chunk_idx = 0
        for md_doc in md_docs:
            # 构造完整标题路径
            header_path = " > ".join(
                str(v) for k, v in md_doc.metadata.items() if k.startswith("h")
            )

            # 第二阶段：对长块再用递归切分
            sub_pieces = self._sub_splitter.split_text(md_doc.page_content)
            for piece in sub_pieces:
                chunks.append(
                    Chunk(
                        content=piece,
                        metadata={
                            "chunk_index": chunk_idx,
                            "strategy": "markdown_header",
                            "header_path": header_path or "(no-header)",
                        },
                    )
                )
                chunk_idx += 1

        logger.info(
            "MarkdownHeaderSplitter 切分完成: {} 字符 -> {} 块",
            len(text), len(chunks),
        )
        return chunks


# ---------- 具体策略：基于语义跳变的智能分块 ----------
class SemanticSplitter(BaseSplitter):
    """
    基于 Embedding 余弦距离的语义分块器

    思路（参考 LangChain SemanticChunker / Greg Kamradt 的方法）：
    1. 先把文档按标点切成"句子"列表
    2. 对每个句子做 Embedding（批量调用通义/Mock）
    3. 计算"每两个相邻句子之间的余弦距离"——距离越大说明话题切换越剧烈
    4. 取这些距离的高分位数（如 95%）作为切分阈值
    5. 在跳变度 > 阈值的位置切一刀
    6. 任何单块超过 chunk_size 时，用 RecursiveSplitter 二次细切作兜底

    优劣：
    + 质量最高（按真实语义边界切，而非字符或标题）
    - 慢（要调 N/10 次 Embedding API）
    - 有成本（消耗 Embedding token）
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 80,
        breakpoint_percentile: int = 95,
        min_chunk_chars: int = 80,
    ):
        if not 50 <= breakpoint_percentile <= 99:
            raise ValueError("breakpoint_percentile 必须在 50-99 之间")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.breakpoint_percentile = breakpoint_percentile
        self.min_chunk_chars = min_chunk_chars

    # ---------- 内部工具 ----------
    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        """
        把文本按句末标点（中英文）切成句子列表，保留标点。

        策略：用正则在标点【后面】切分。
        例："你好。今天天气真不错！" → ["你好。", "今天天气真不错！"]
        """
        import re
        # 匹配中文/英文句末标点后的位置作为分割点（向后看）
        # 保留 \n\n 作为段落级别的强切分点
        pattern = r"(?<=[。！？!?])\s*|(?<=\n)\s*"
        raw = re.split(pattern, text)
        # 过滤空串与纯空白
        sentences = [s.strip() for s in raw if s and s.strip()]
        return sentences

    @staticmethod
    def _cosine_distance(a: List[float], b: List[float]) -> float:
        """返回余弦距离 ∈ [0, 2]，0 表示完全相似"""
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 1.0
        return 1.0 - dot / (na * nb)

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        """简易分位数（线性插值），避免引入 numpy 强依赖"""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * (pct / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        if f == c:
            return sorted_vals[f]
        return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

    def _refine_oversized(self, content: str) -> List[str]:
        """单块超过 chunk_size 时用 RecursiveSplitter 二次细切"""
        if len(content) <= self.chunk_size:
            return [content]
        sub_splitter = RecursiveSplitter(
            chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap,
        )
        return [c.content for c in sub_splitter.split(content)]

    # ---------- 主流程 ----------
    def split(self, text: str) -> List[Chunk]:
        # 延迟导入 embedder，避免循环依赖（embedder 在 rag 包，splitter 也在）
        from app.rag.embedder import get_embedder

        # 第 1 步：句子切分
        sentences = self._split_into_sentences(text)
        if len(sentences) <= 1:
            # 文本太短，直接返回一整块
            return [
                Chunk(
                    content=text.strip(),
                    metadata={"chunk_index": 0, "strategy": "semantic", "note": "text_too_short"},
                )
            ]

        # 第 2 步：批量向量化
        embedder = get_embedder()
        embeddings = embedder.embed_texts(sentences)

        # 第 3 步：相邻句子余弦距离
        distances = [
            self._cosine_distance(embeddings[i], embeddings[i + 1])
            for i in range(len(embeddings) - 1)
        ]

        # 第 4 步：高分位阈值（语义跳变点）
        threshold = self._percentile(distances, self.breakpoint_percentile)
        logger.info(
            "SemanticSplitter: {} 句, 距离 P{}={:.4f}",
            len(sentences), self.breakpoint_percentile, threshold,
        )

        # 第 5 步：按跳变点切分
        # distances[i] 是 sentences[i] 与 sentences[i+1] 的距离
        # 若 > 阈值，sentences[i+1] 开始一个新块
        break_indices = [
            i + 1 for i, d in enumerate(distances) if d > threshold
        ]
        break_indices.append(len(sentences))  # 末尾哨兵

        raw_chunks: List[str] = []
        start = 0
        for bp in break_indices:
            content = "".join(sentences[start:bp])
            if not content.strip():
                start = bp
                continue
            # 太短的小段并入前一个，避免碎片
            if len(content) < self.min_chunk_chars and raw_chunks:
                raw_chunks[-1] += content
            else:
                raw_chunks.append(content)
            start = bp

        # 第 6 步：单块超大兜底
        chunks: List[Chunk] = []
        idx = 0
        for raw in raw_chunks:
            for piece in self._refine_oversized(raw):
                chunks.append(
                    Chunk(
                        content=piece,
                        metadata={
                            "chunk_index": idx,
                            "strategy": "semantic",
                            "breakpoint_pct": self.breakpoint_percentile,
                        },
                    )
                )
                idx += 1

        logger.info(
            "SemanticSplitter 切分完成: {} 字符 -> {} 块 (跳变点 {} 个)",
            len(text), len(chunks), len(break_indices) - 1,
        )
        return chunks


# ---------- 工厂函数 ----------
def get_splitter(
    strategy: ChunkStrategy,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> BaseSplitter:
    """
    根据策略类型返回对应的 Splitter 实例

    :param strategy: 分块策略枚举（来自 KnowledgeBase.chunk_strategy）
    :param chunk_size: 分块大小
    :param chunk_overlap: 分块重叠
    """
    if strategy == ChunkStrategy.RECURSIVE:
        return RecursiveSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if strategy == ChunkStrategy.MARKDOWN_HEADER:
        return MarkdownHeaderSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if strategy == ChunkStrategy.SEMANTIC:
        return SemanticSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    raise ValueError(f"未知的分块策略: {strategy}")
