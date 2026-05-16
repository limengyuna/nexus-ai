"""
Skill 相关 Schemas
"""
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    """技能信息（只读展示）"""
    name: str
    description: str
    required_tools: List[str] = Field(default_factory=list)
    trigger_keywords: List[str] = Field(default_factory=list)


class SkillTestRequest(BaseModel):
    """技能测试请求"""
    user_input: str = Field(..., min_length=1, max_length=1000)
    # 可选上下文：某些 Skill（如 document_summarizer）需要传 kb_id
    kb_id: int | None = Field(None, description="关联的知识库 ID（部分 Skill 需要）")


class SkillTestResponse(BaseModel):
    """技能测试响应（不入会话历史）"""
    skill_name: str
    answer: str
    tool_calls: List[Any] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
