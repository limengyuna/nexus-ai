"""
记忆事实 Pydantic 响应与请求 Schema 
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class MemoryFactOut(BaseModel):
    """记忆事实输出模型"""
    id: int = Field(..., description="记忆事实唯一 ID")
    user_id: int = Field(..., description="用户 ID")
    session_id: Optional[int] = Field(None, description="来源会话 ID")
    kb_id: Optional[int] = Field(None, description="关联知识库 ID（NULL 为全局记忆）")
    fact_type: str = Field(..., description="事实类型")
    content: str = Field(..., description="事实文本内容")
    importance: float = Field(..., description="重要性评分（0.0 ~ 1.0）")
    access_count: int = Field(..., description="被检索并使用的次数")
    last_accessed_at: Optional[datetime] = Field(None, description="最后一次被检索访问时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")

    model_config = ConfigDict(from_attributes=True)
