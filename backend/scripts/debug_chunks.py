"""调试：查看 plan.md 切分出来的 chunk 内容（找含 MCP 的）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.knowledge_base import ChunkStrategy
from app.rag.parser import parse_document
from app.rag.splitter import get_splitter

text = parse_document(Path(__file__).parent.parent.parent / "plan.md")
splitter = get_splitter(ChunkStrategy.MARKDOWN_HEADER, chunk_size=800, chunk_overlap=80)
chunks = splitter.split(text)

print(f"\n总分块数: {len(chunks)}\n")

# 找含 MCP 的 chunk
mcp_chunks = [(i, c) for i, c in enumerate(chunks) if "MCP" in c.content]
print(f"含 'MCP' 的 chunk 数: {len(mcp_chunks)}\n")

for i, c in mcp_chunks[:5]:
    print(f"\n{'=' * 60}")
    print(f"Chunk #{i} | len={len(c.content)} | metadata={c.metadata}")
    print("-" * 60)
    print(c.content[:500])
    if len(c.content) > 500:
        print("...")
