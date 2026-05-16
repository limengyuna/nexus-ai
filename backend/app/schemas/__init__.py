"""
Pydantic 校验模型集合

按业务领域拆分文件，统一在此导出。
"""
from app.schemas.chat import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionOut,
)
from app.schemas.common import ApiResponse, TokenResponse
from app.schemas.document import (
    DocumentOut,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.schemas.task import TaskRecordOut
from app.schemas.user import UserCreate, UserLogin, UserOut

__all__ = [
    # 通用
    "ApiResponse",
    "TokenResponse",
    # 用户
    "UserCreate",
    "UserLogin",
    "UserOut",
    # 知识库
    "KnowledgeBaseCreate",
    "KnowledgeBaseUpdate",
    "KnowledgeBaseOut",
    # 文档
    "DocumentOut",
    "SearchRequest",
    "SearchResponse",
    "SearchHit",
    # 任务
    "TaskRecordOut",
    # 对话
    "ChatSessionCreate",
    "ChatSessionOut",
    "ChatMessageOut",
    "ChatRequest",
    "ChatResponse",
]
