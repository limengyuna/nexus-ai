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
    is_archived: bool = False
    created_at: datetime


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResumeRequest(BaseModel):
    """中断恢复请求（仅用于工具审批场景）

    注：用户主动取消不再走 resume 通道——取消即终止当前轮次，下次发消息走新一轮 chat_stream。
    跨轮记忆通过 ChatMessage.task_plan_meta 字段持久化，新一轮 supervisor 规划阶段读取它判断要跳过哪些 step。
    """
    user_msg_id: int = Field(..., description="被中断对话轮次对应的原始用户消息 ID（thread_id 来源）")
    action: str = Field(..., pattern="^(approve|reject)$", description="工具审批动作：approve / reject")
    reason: Optional[str] = Field(None, max_length=500, description="拒绝/批准理由（可选，发给 LLM 作为上下文）")
    edited_args: Optional[dict] = Field(None, description="批准时可选：用户编辑后的工具参数（如修改文件路径）")


class ChatResponse(BaseModel):
    """非流式对话响应（含完整 Agent 思考过程，便于前端展示）"""
    message: ChatMessageOut                   # Agent 回复消息
    intent: str = ""                          # Router 决策
    route_reason: str = ""                    # 路由理由
    skill_used: Optional[str] = None          # 命中的 Skill
    tool_calls: List[Any] = []                # 工具调用详情
    retrieved_docs: List[Any] = []            # RAG 检索结果
    execution_trace: List[Any] = []           # 完整执行链路
