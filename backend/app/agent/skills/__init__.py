"""
技能编排层 (Skills)

设计意图：
- Tool 是原子能力（单一职责），Skill 是多 Tool 的编排组合 + 专用 Prompt
- Router Agent 优先匹配 Skill，匹配不到再降级到单 Tool 调用
- Skill 在内部可以调用 LLM 做多步推理，或者按固定流程编排 Tool

例子：
- TravelPlannerSkill = weather Tool + 景点查询Tool + 行程规划 prompt
- DataAnalystSkill   = SQL Tool + 数据处理Tool + 报告 prompt
"""
from app.agent.skills.registry import (
    BaseSkill,
    SkillRegistry,
    get_skill,
    list_skills,
    register_skill,
    skill_registry,
)

# 显式导入触发注册
from app.agent.skills import (  # noqa: F401
    data_analyst,
    document_summarizer,
    email_drafter,
    research_assistant,
    travel_planner,
)

__all__ = [
    "BaseSkill",
    "SkillRegistry",
    "register_skill",
    "get_skill",
    "list_skills",
    "skill_registry",
]
