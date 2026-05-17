"""
旅行规划技能

编排：
1. 调用 weather Tool 获取目的地天气
2. 拼接专用 Prompt，让 LLM 生成完整旅行建议

体现 Skill = Tool + Prompt 的组合编排思想。
"""
import re
from typing import Any, Dict, Optional

from loguru import logger

from app.agent.skills.registry import BaseSkill, register_skill


@register_skill
class TravelPlannerSkill(BaseSkill):
    """旅行规划技能：天气查询 + 智能行程建议"""

    name = "travel_planner"
    description = "为指定城市/目的地生成旅行规划建议，含当地天气、穿衣建议、景点推荐、出行注意事项"
    required_tools = ["get_weather"]
    trigger_keywords = ["旅行", "旅游", "出行", "去玩", "行程", "出差", "trip", "travel"]

    # 简单的中文城市提取（前缀触发词）
    _CITY_PATTERN = re.compile(r"去(.*?)(?:旅|玩|出差|的旅行|的旅游|$)")

    def execute(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        context_messages = context.get("context_messages", [])

        # ---------- 1. 简单提取目的地 ----------
        city = self._extract_city(user_input)
        if not city:
            return {
                "answer": "请告诉我具体想去哪个城市，例如'我想去北京旅行'。",
                "tool_calls": [],
                "meta": {"skill": self.name, "missing": "city"},
            }

        # ---------- 2. 调天气工具 ----------
        weather = self._call_tool("get_weather", city=city)
        logger.info("[Skill:{}] 已获取 {} 天气: {}", self.name, city, weather)

        tool_calls = [
            {
                "name": "get_weather",
                "kind": "tool",
                "arguments": {"city": city},
                "result": weather,
            }
        ]

        # ---------- 3. 用 LLM 组装专业回答 ----------
        # 延迟导入避免循环
        from app.agent.llm import get_llm

        llm = get_llm()
        # 拼接对话历史摘要，让 LLM 感知用户之前提到的时间、偏好等信息
        history_hint = ""
        if context_messages:
            parts = []
            for msg in context_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    parts.append(f"{role}: {content}")
            if parts:
                history_hint = "\n对话历史：\n" + "\n".join(parts[-6:]) + "\n\n"

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "你是一位专业的旅行规划顾问。基于用户的目的地与当地天气，"
                    "给出贴心实用的旅行建议，包含：1) 天气解读和穿衣建议；"
                    "2) 行程节奏建议（半天/全天/多日）；3) 必备物品；"
                    "4) 注意事项。结合对话历史中用户提到的时间、人数、偏好等信息。回答简明有条理。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{history_hint}"
                    f"用户原始问题：{user_input}\n"
                    f"目的地：{city}\n"
                    f"当地天气：{weather}\n\n"
                    "请用中文给出旅行建议。"
                ),
            },
        ]
        answer = llm.complete(messages=prompt_messages, temperature=0.5, max_tokens=600)

        return {
            "answer": answer,
            "tool_calls": tool_calls,
            "meta": {"skill": self.name, "city": city},
        }

    # ---------- 内部工具 ----------
    def _extract_city(self, text: str) -> Optional[str]:
        m = self._CITY_PATTERN.search(text)
        if m:
            city = m.group(1).strip()
            # 过滤掉太短或包含助词的提取
            if 1 < len(city) < 20 and not city.endswith(("个", "下", "里", "趟")):
                return city
        # 兜底：如果 user_input 像"北京天气"，直接提取前 4 字符
        for token in ["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "南京",
                      "西安", "武汉", "苏州", "厦门", "三亚", "青岛", "天津"]:
            if token in text:
                return token
        return None
