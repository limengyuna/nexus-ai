"""
对话相关 Schemas
"""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat import AgentSource, MessageRole


class ChatSessionCreate(BaseModel):
    """创建会话请求"""
    title: str = Field(default="新对话", max_length=255)
    kb_id: Optional[int] = Field(None, description="关联的知识库 ID（启用 RAG 用）")


class ChatSessionUpdate(BaseModel):
    """更新会话请求（目前仅支持改标题；预留 kb_id 切换）"""
    title: Optional[str] = Field(None, max_length=255)
    kb_id: Optional[int] = Field(None, description="关联的知识库 ID")


class ChatSessionOut(BaseModel):
    """会话信息"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    user_id: int
    kb_id: Optional[int]
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(BaseModel):
    """单条消息信息"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: MessageRole
    content: str
    agent_source: Optional[AgentSource]
    tool_calls_json: Optional[Any]
    token_usage: Optional[int]
    created_at: datetime


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    """非流式对话响应（含完整 Agent 思考过程，便于前端展示）"""
    message: ChatMessageOut                   # Agent 回复消息
    intent: str = ""                          # Router 决策
    route_reason: str = ""                    # 路由理由
    skill_used: Optional[str] = None          # 命中的 Skill
    tool_calls: List[Any] = []                # 工具调用详情
    retrieved_docs: List[Any] = []            # RAG 检索结果
    execution_trace: List[Any] = []           # 完整执行链路
