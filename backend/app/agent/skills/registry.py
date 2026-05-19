"""
Skill 基类与注册中心
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from loguru import logger


# ---------- 技能基类 ----------
class BaseSkill(ABC):
    """
    技能基类

    子类需声明：
    - name:              唯一名（snake_case）
    - description:       描述（给 Router 看的）
    - required_tools:    所需的原子工具名列表
    - trigger_keywords:  触发关键词（Router 用关键词做轻量匹配，命中再交给 LLM 二次判断）

    子类实现：
    - execute(user_input, context) -> dict
    """

    name: str = ""
    description: str = ""
    required_tools: List[str] = []
    trigger_keywords: List[str] = []
    allow_with_kb: bool = False  # 有 KB 时是否也允许关键词匹配触发

    @abstractmethod
    def execute(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行技能

        :param user_input: 用户原始输入
        :param context: 可选上下文（如 RAG 检索结果、历史对话摘要等）
        :return: {"answer": str, "tool_calls": [...], "meta": {...}}
        """
        raise NotImplementedError

    # ---------- 通用工具：调用注册的原子 Tool ----------
    def _call_tool(self, tool_name: str, **kwargs) -> Any:
        # 延迟导入避免循环
        from app.agent.tools import get_tool

        tool = get_tool(tool_name)
        if tool is None:
            raise ValueError(f"工具不存在: {tool_name}")
        return tool.run(**kwargs)


# ---------- 注册中心 ----------
class SkillRegistry:
    """全局技能注册表"""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        if not skill.name:
            raise ValueError("Skill 必须定义 name")
        if skill.name in self._skills:
            logger.warning("技能 {} 已注册，覆盖", skill.name)
        self._skills[skill.name] = skill
        logger.info("✓ 注册技能: {} (需要工具: {})", skill.name, skill.required_tools)

    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list(self) -> List[BaseSkill]:
        return list(self._skills.values())

    def match_by_keywords(self, user_input: str, has_kb: bool = False) -> Optional[BaseSkill]:
        """
        关键词预匹配（O(n)）
        让 Router 在调 LLM 之前先用关键词快速判断有没有候选 Skill，
        节省一次不必要的 LLM 调用。

        :param has_kb: 是否绑定了知识库，有 KB 时只匹配 allow_with_kb=True 的 Skill
        """
        lower = user_input.lower()
        for skill in self._skills.values():
            # 有 KB 时只允许白名单 Skill 通过关键词匹配
            if has_kb and not skill.allow_with_kb:
                continue
            if any(kw.lower() in lower for kw in skill.trigger_keywords):
                return skill
        return None

    def to_choices_for_router(self) -> List[Dict[str, str]]:
        """给 Router LLM 看的"技能菜单" """
        return [
            {"name": s.name, "description": s.description}
            for s in self._skills.values()
        ]

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """
        将所有 Skill 转换为 OpenAI Function Calling 格式。

        每个 Skill 作为一个"工具"暴露给 LLM，参数固定为 user_input。
        LLM 选择调用某个 Skill 后，由 tool_agent 分发执行。
        """
        schemas: List[Dict[str, Any]] = []
        for s in self._skills.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": f"skill_{s.name}",
                    "description": f"[技能] {s.description}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_input": {
                                "type": "string",
                                "description": "用户的原始输入或经过改写的请求",
                            },
                        },
                        "required": ["user_input"],
                    },
                },
            })
        return schemas


# 全局单例
skill_registry = SkillRegistry()


# ---------- 装饰器 ----------
def register_skill(skill_cls: Type[BaseSkill]) -> Type[BaseSkill]:
    skill_registry.register(skill_cls())
    return skill_cls


def get_skill(name: str) -> Optional[BaseSkill]:
    return skill_registry.get(name)


def list_skills() -> List[BaseSkill]:
    return skill_registry.list()
