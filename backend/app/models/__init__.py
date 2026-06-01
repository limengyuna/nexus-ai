"""
SQLAlchemy ORM 模型集合

统一导出所有模型，便于：
1. Alembic autogenerate 自动发现所有表
2. 业务代码通过 from app.models import User 直接导入
"""
from app.models.base import TimestampMixin
from app.models.user import User, UserRole
from app.models.knowledge_base import KnowledgeBase, ChunkStrategy
from app.models.document import Document, DocumentStatus
from app.models.chat import ChatSession, ChatMessage, MessageRole, AgentSource
from app.models.task import TaskRecord, TaskStatus, TaskType
from app.models.mcp_server import MCPServerConfig, MCPTransportType
from app.models.memory import MemoryFact, MemoryFactType
from app.models.memory_profile import MemorySlot, UserMemorySlotValue, MemoryCandidate

__all__ = [
    # Mixin
    "TimestampMixin",
    # 用户
    "User",
    "UserRole",
    # 知识库
    "KnowledgeBase",
    "ChunkStrategy",
    # 文档
    "Document",
    "DocumentStatus",
    # 对话
    "ChatSession",
    "ChatMessage",
    "MessageRole",
    "AgentSource",
    # 记忆事实
    "MemoryFact",
    "MemoryFactType",
    # 结构化记忆档案
    "MemorySlot",
    "UserMemorySlotValue",
    "MemoryCandidate",
    # 异步任务
    "TaskRecord",
    "TaskStatus",
    "TaskType",
    # MCP
    "MCPServerConfig",
    "MCPTransportType",
]
