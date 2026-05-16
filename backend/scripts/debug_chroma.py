"""调试：直接用 chromadb 客户端复现 RAG 流程，定位异常环节"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb

from app.rag.embedder import get_embedder

embedder = get_embedder()

# 用真实通义 embedding 准备数据
texts = [
    "MCP 协议层（Model Context Protocol）基于 Anthropic 发布的 MCP 开放标准，实现双向集成",
    "PostgreSQL 是企业级关系数据库",
    "Vue 3 + Vite 前端开发框架",
]
embs = embedder.embed_texts(texts)
print(f"texts={len(texts)} 维度={len(embs[0])}\n")

# 直接 HTTP 连 chroma
client = chromadb.HttpClient(host="localhost", port=8001)

# 先清理
try:
    client.delete_collection(name="debug_test")
except Exception:
    pass

# 创建 collection
col = client.get_or_create_collection(
    name="debug_test",
    metadata={"hnsw:space": "cosine"},
)
print(f"collection 已创建，count(初始)={col.count()}")

# 写入
col.upsert(
    ids=["a", "b", "c"],
    documents=texts,
    embeddings=embs,
    metadatas=[{"i": i} for i in range(3)],
)
print(f"upsert 后 count={col.count()}\n")

# 查询
query_vec = embedder.embed_query("什么是 MCP 协议？")
result = col.query(query_embeddings=[query_vec], n_results=3)

print("查询结果：")
for chunk_id, doc, dist in zip(result["ids"][0], result["documents"][0], result["distances"][0]):
    print(f"  id={chunk_id} distance={dist:.4f}  text={doc[:40]}...")

# 清理
client.delete_collection(name="debug_test")
print("\n清理完毕")
