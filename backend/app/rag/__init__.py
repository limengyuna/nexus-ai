"""
RAG (Retrieval Augmented Generation) 模块

四大子模块各司其职，通过抽象接口解耦：
- parser:       文档解析（多种文件格式 → 纯文本）
- splitter:     文本分块（策略模式，支持多种切分策略）
- embedder:     向量化（多 Provider，自动回退）
- vector_store: 向量存储（抽象接口 + ChromaDB 实现）
"""
from app.rag.embedder import BaseEmbedder, get_embedder
from app.rag.parser import DocumentParser, parse_document
from app.rag.splitter import BaseSplitter, get_splitter
from app.rag.vector_store import BaseVectorStore, get_vector_store

__all__ = [
    # parser
    "DocumentParser",
    "parse_document",
    # splitter
    "BaseSplitter",
    "get_splitter",
    # embedder
    "BaseEmbedder",
    "get_embedder",
    # vector store
    "BaseVectorStore",
    "get_vector_store",
]
