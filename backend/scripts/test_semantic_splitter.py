"""
对比三种分块策略对同一文档的切分效果

输出每种策略的：
- 分块数量
- 平均/最大/最小块大小
- 第一块和最后一块的预览
- 切分耗时
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.knowledge_base import ChunkStrategy
from app.rag.parser import parse_document
from app.rag.splitter import get_splitter


def run_one(strategy: ChunkStrategy, text: str):
    print(f"\n{'=' * 70}\n>>> {strategy.value.upper()} 策略\n{'=' * 70}")

    if strategy == ChunkStrategy.SEMANTIC:
        # semantic 默认 chunk_size 800
        splitter = get_splitter(strategy, chunk_size=800, chunk_overlap=80)
    else:
        splitter = get_splitter(strategy, chunk_size=500, chunk_overlap=50)

    t0 = time.time()
    chunks = splitter.split(text)
    elapsed = time.time() - t0

    sizes = [len(c.content) for c in chunks]
    avg = sum(sizes) // len(sizes) if sizes else 0
    print(f"分块数: {len(chunks)}")
    print(f"块大小: avg={avg}  min={min(sizes)}  max={max(sizes)}  chars")
    print(f"耗时: {elapsed:.2f}s")
    print(f"\n[首块预览 / {len(chunks[0].content)} chars]")
    print(chunks[0].content[:200].replace("\n", " ") + ("..." if len(chunks[0].content) > 200 else ""))
    print(f"\n[末块预览 / {len(chunks[-1].content)} chars]")
    print(chunks[-1].content[:200].replace("\n", " ") + ("..." if len(chunks[-1].content) > 200 else ""))
    if strategy == ChunkStrategy.SEMANTIC and chunks:
        print(f"\n[语义切分元数据] breakpoint_pct={chunks[0].metadata.get('breakpoint_pct')}")


def main():
    text = parse_document(Path(__file__).parent.parent.parent / "plan.md")
    print(f"原文档长度: {len(text)} 字符\n")

    for s in [ChunkStrategy.RECURSIVE, ChunkStrategy.MARKDOWN_HEADER, ChunkStrategy.SEMANTIC]:
        run_one(s, text)


if __name__ == "__main__":
    main()
