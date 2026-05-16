"""调试：直接计算几个文本的 embedding 余弦相似度，判断是 embedding 异常还是 chroma 异常"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import math

from app.rag.embedder import get_embedder

embedder = get_embedder()
print(f"Embedder 类型: {type(embedder).__name__}\n")

texts = [
    "什么是 MCP 协议？",                                          # 0: query
    "MCP 协议层（Model Context Protocol）基于 Anthropic 发布的 MCP 开放标准",  # 1: 高度相关
    "MCP 协议层 暴露知识库和工具能力",                              # 2: 高度相关
    "PostgreSQL 是关系数据库",                                    # 3: 完全无关
    "Vue 3 + Vite 前端开发",                                      # 4: 完全无关
]

vectors = embedder.embed_texts(texts)

# 计算每个向量的 L2 范数
def l2_norm(v):
    return math.sqrt(sum(x * x for x in v))

# 余弦相似度
def cosine_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (l2_norm(a) * l2_norm(b))

print(f"{'文本':<60s} | L2 范数")
print("-" * 80)
for i, (t, v) in enumerate(zip(texts, vectors)):
    print(f"{i}: {t[:55]:<60s} | {l2_norm(v):.4f}")

print(f"\n余弦相似度 (越大越相似)")
print("-" * 80)
q = vectors[0]
for i in range(1, len(vectors)):
    sim = cosine_sim(q, vectors[i])
    dist = 1 - sim
    print(f"sim(query, '{texts[i][:30]}'): {sim:.4f}  | cosine_distance: {dist:.4f}")
