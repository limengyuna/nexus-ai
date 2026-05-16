"""
Skills 只读 API

接口：
- GET  /skills                列出所有已注册的 Skill（含描述、依赖工具、触发关键词）
- POST /skills/{name}/test    直接调用 Skill 执行（不入会话），用于前端"测试一下"按钮
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.agent.skills import skill_registry  # 触发注册的副作用
from app.agent.skills.registry import get_skill, list_skills
from app.agent.tools.registry import get_tool
from app.core.ratelimit import LIMIT_LLM, limiter
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.skill import SkillInfo, SkillTestRequest, SkillTestResponse

router = APIRouter(prefix="/skills", tags=["技能"])


@router.get(
    "",
    response_model=ApiResponse[List[SkillInfo]],
    summary="列出所有已注册的 Skill",
)
def list_all_skills(current_user: User = Depends(get_current_user)):
    """
    返回当前后端代码中注册的全部 Skills。
    Skill 是工程定义，每次进程启动从代码加载，不持久化到数据库。
    """
    skills = list_skills()
    return ApiResponse.ok(
        data=[
            SkillInfo(
                name=s.name,
                description=s.description,
                required_tools=list(s.required_tools),
                trigger_keywords=list(s.trigger_keywords),
            )
            for s in skills
        ]
    )


@router.post(
    "/{skill_name}/test",
    response_model=ApiResponse[SkillTestResponse],
    summary="直接执行某个 Skill（用于前端预览能力）",
)
@limiter.limit(LIMIT_LLM)
def test_skill(
    request: Request,
    skill_name: str,
    payload: SkillTestRequest,
    current_user: User = Depends(get_current_user),
):
    """
    跳过 Router 直接调用指定 Skill。

    用途：让用户在 SkillsView 里点"测试一下"，看 Skill 的真实执行效果，
    不会污染对话历史，也不会保存到任何 session。
    """
    skill = get_skill(skill_name)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill 不存在: {skill_name}")

    # 校验所需 Tool 都已注册
    missing_tools = [t for t in skill.required_tools if get_tool(t) is None]
    if missing_tools:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill 依赖的工具未注册: {missing_tools}",
        )

    try:
        # 把可选上下文（如 kb_id）透传给 Skill
        context = {}
        if payload.kb_id is not None:
            context["kb_id"] = payload.kb_id
        result = skill.execute(payload.user_input, context=context or None)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill 执行失败: {e}",
        )

    return ApiResponse.ok(
        data=SkillTestResponse(
            skill_name=skill_name,
            answer=result.get("answer", ""),
            tool_calls=result.get("tool_calls", []),
            meta=result.get("meta", {}),
        )
    )
