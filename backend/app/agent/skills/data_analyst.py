"""
数据分析技能

编排：
1. 让 LLM 从用户问题中抽取需要计算的表达式
2. 调用 calculator Tool 精确求值
3. 把结果交还 LLM 做自然语言解读

体现：Skill 多步调用 LLM + Tool 配合，提供单 Tool 无法实现的智能体验。
"""
import json
from typing import Any, Dict, List, Optional

from loguru import logger

from app.agent.skills.registry import BaseSkill, register_skill


@register_skill
class DataAnalystSkill(BaseSkill):
    """数据分析技能：从自然语言提取计算需求 → 精确计算 → 智能解读"""

    name = "data_analyst"
    description = "进行数据计算与分析，处理用户口语化的数学问题，自动转换为精确表达式并给出解读"
    required_tools = ["calculate"]
    # 只用明确指向数学计算的关键词，避免太宽泛的"数据/统计"误命中（如"向量数据库"）
    trigger_keywords = ["计算一下", "算一下", "帮我算", "等于多少", "几等于几", "calculate"]

    def execute(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from app.agent.llm import get_llm
        llm = get_llm()

        # ---------- 1. LLM 抽取数学表达式列表 ----------
        extract_messages = [
            {
                "role": "system",
                "content": (
                    "你是表达式抽取器。把用户的自然语言数学问题转换为可被 Python eval 安全求值的表达式。"
                    "支持 + - * / ** %、sqrt/log/sin/cos 等函数、常量 pi/e。"
                    '严格输出 JSON 格式：{"expressions": ["表达式1", "表达式2", ...]}'
                    "如果用户问题不包含可计算的数学内容，输出空数组。"
                ),
            },
            {"role": "user", "content": user_input},
        ]
        extract_raw = llm.complete(
            messages=extract_messages,
            temperature=0,
            response_format={"type": "json_object"},
        )

        try:
            extracted = json.loads(extract_raw)
            expressions: List[str] = extracted.get("expressions", [])
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning("DataAnalystSkill 表达式抽取 JSON 解析失败: {} | raw={}", e, extract_raw)
            expressions = []

        # ---------- 2. 调用 calculator 工具求值 ----------
        tool_calls: List[Dict[str, Any]] = []
        results: List[Dict[str, Any]] = []
        for expr in expressions:
            result = self._call_tool("calculate", expression=expr)
            tool_calls.append({
                "name": "calculate",
                "kind": "tool",
                "arguments": {"expression": expr},
                "result": result,
            })
            results.append(result)

        # ---------- 3. LLM 解读 ----------
        if not results:
            # 没有可计算内容，直接 LLM 自由回答
            interpret_messages = [
                {"role": "system", "content": "你是一位数据分析师，用简洁专业的语言回答用户的数据问题。"},
                {"role": "user", "content": user_input},
            ]
        else:
            interpret_messages = [
                {
                    "role": "system",
                    "content": "你是一位数据分析师。基于精确计算结果，给出简洁的中文解读，必要时给出业务洞察。",
                },
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{user_input}\n\n"
                        f"我已经精确计算得到以下结果：\n"
                        f"{json.dumps(results, ensure_ascii=False, indent=2)}\n\n"
                        "请用中文回答用户。"
                    ),
                },
            ]
        answer = llm.complete(messages=interpret_messages, temperature=0.3, max_tokens=500)

        return {
            "answer": answer,
            "tool_calls": tool_calls,
            "meta": {
                "skill": self.name,
                "expressions": expressions,
            },
        }
