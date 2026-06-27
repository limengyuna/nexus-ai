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

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 80,
        min_chunk_chars: int = 200,
        parent_chunk_size: int = 2500,
    ):
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
        # 父块切分器：无 overlap，按自然语言边界将超长标题内容切成多个父块
        # 父块只用于生成时提供上下文，不进行向量检索，因此无需 overlap
        self._parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=0,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.parent_chunk_size = parent_chunk_size
        # 最小块字符数：低于此阈值的小块会尝试与相邻块合并
        # 用于解决中文 PDF / DOCX 中 Unstructured 误把正文段落识别为 Title 导致的过度碎片化
        self.min_chunk_chars = min_chunk_chars

    def split(self, text: str) -> List[Chunk]:
        # ---------- 第一阶段：按标题切分（得到 parent 级别的块） ----------
        md_docs = self._md_splitter.split_text(text)

        # ---------- 第二阶段：把每个 md_doc 转成原始候选块 ----------
        # 候选块结构：{content, header_path, parent_content}
        #
        # 分层切分策略：
        # 1. 若标题下的内容 <= parent_chunk_size，整体作为一个父块，再切子块（原有逻辑）
        # 2. 若标题下的内容 > parent_chunk_size，先用 parent_splitter 切成多个父块（无 overlap），
        #    再在每个父块内用 sub_splitter 切子块。
        #    每个子块只记录所在父块的内容（<= parent_chunk_size），
        #    保证 parent_content 有上限，避免 ChromaDB metadata 过大。
        raw_candidates: List[Dict] = []
        for md_doc in md_docs:
            header_path = " > ".join(
                str(v) for k, v in md_doc.metadata.items() if k.startswith("h")
            )
            full_content = md_doc.page_content

            # 如果内容超过父块上限，先切父块；否则整体作为一个父块
            if len(full_content) > self.parent_chunk_size:
                parent_blocks = self._parent_splitter.split_text(full_content)
                logger.debug(
                    "MarkdownHeaderSplitter: 标题块 {} 字 > 父块上限 {} 字，切分为 {} 个父块",
                    len(full_content), self.parent_chunk_size, len(parent_blocks),
                )
            else:
                parent_blocks = [full_content]

            for parent_block in parent_blocks:
                # 在父块内部切子块（child 级别）
                sub_pieces = self._sub_splitter.split_text(parent_block)
                has_children = len(sub_pieces) > 1

                for piece in sub_pieces:
                    raw_candidates.append({
                        "content": piece,
                        "header_path": header_path or "(no-header)",
                        # 只有父块内被进一步切分时才记录 parent_content
                        # parent_block 字数 <= parent_chunk_size，ChromaDB metadata 安全
                        "parent_content": parent_block if has_children else None,
                    })

        # ---------- 第三阶段：贪心合并小块 ----------
        # 规则：若当前累积块字符数 < min_chunk_chars，
        # 且与下一个候选块合并后不超 chunk_size，则合并。
        # 合并后丢弃 parent_content（因为已经聚合了足够上下文）。
        # header_path 保留首个非空者，避免丢失章节信息。
        merged: List[Dict] = []
        buffer: Dict | None = None
        for cand in raw_candidates:
            if buffer is None:
                buffer = dict(cand)
                continue

            buf_len = len(buffer["content"])
            cand_len = len(cand["content"])

            should_merge = (
                buf_len < self.min_chunk_chars
                and buf_len + cand_len + 1 <= self.chunk_size
            )
            if should_merge:
                buffer["content"] = buffer["content"] + "\n" + cand["content"]
                # 合并块的 header_path：优先保留 buffer 的（更靠前 = 更接近 parent）
                if not buffer["header_path"] or buffer["header_path"] == "(no-header)":
                    buffer["header_path"] = cand["header_path"]
                # 合并后块已自带充足上下文，不再标记 parent_content
                buffer["parent_content"] = None
            else:
                merged.append(buffer)
                buffer = dict(cand)
        if buffer is not None:
            merged.append(buffer)

        # ---------- 第四阶段：构造最终 Chunk ----------
        chunks: List[Chunk] = []
        for idx, m in enumerate(merged):
            metadata = {
                "chunk_index": idx,
                "strategy": "markdown_header",
                "header_path": m["header_path"],
            }
            if m["parent_content"]:
                metadata["parent_content"] = m["parent_content"]
            chunks.append(Chunk(content=m["content"], metadata=metadata))

        logger.info(
            "MarkdownHeaderSplitter 切分完成: {} 字符 -> {} 候选块 -> {} 块"
            " (parent-child + 最小块合并 min={})",
            len(text), len(raw_candidates), len(chunks), self.min_chunk_chars,
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


# ---------- 策略默认参数配置 ----------
STRATEGY_DEFAULTS = {
    ChunkStrategy.RECURSIVE: {"chunk_size": 500, "chunk_overlap": 50},
    ChunkStrategy.MARKDOWN_HEADER: {"chunk_size": 800, "chunk_overlap": 80},
    ChunkStrategy.SEMANTIC: {"chunk_size": 800, "chunk_overlap": 80},
}


def get_strategy_defaults(strategy: ChunkStrategy) -> dict:
    """获取指定策略的默认参数"""
    return STRATEGY_DEFAULTS.get(strategy, {"chunk_size": 500, "chunk_overlap": 50})


# ---------- 工厂函数 ----------
def get_splitter(
    strategy: ChunkStrategy,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> BaseSplitter:
    """
    根据策略类型返回对应的 Splitter 实例
    
    参数优先级：传入值 > 策略默认值

    :param strategy: 分块策略枚举（来自 KnowledgeBase.chunk_strategy）
    :param chunk_size: 分块大小（可选，不传则使用策略默认值）
    :param chunk_overlap: 分块重叠（可选，不传则使用策略默认值）
    """
    # 使用策略默认值
    defaults = get_strategy_defaults(strategy)
    size = chunk_size if chunk_size is not None else defaults["chunk_size"]
    overlap = chunk_overlap if chunk_overlap is not None else defaults["chunk_overlap"]
    
    if strategy == ChunkStrategy.RECURSIVE:
        return RecursiveSplitter(chunk_size=size, chunk_overlap=overlap)
    if strategy == ChunkStrategy.MARKDOWN_HEADER:
        return MarkdownHeaderSplitter(chunk_size=size, chunk_overlap=overlap)
    if strategy == ChunkStrategy.SEMANTIC:
        return SemanticSplitter(chunk_size=size, chunk_overlap=overlap)
    raise ValueError(f"未知的分块策略: {strategy}")
