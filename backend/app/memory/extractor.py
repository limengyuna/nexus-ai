"""
L2 记忆事实抽取器

负责使用 LLM 从工具调用错误和对话历史中抽取结构化的记忆事实（Facts）。
"""
import json
from typing import Any, Dict, List, Optional
from loguru import logger

from app.agent.llm import get_llm_fast
from app.models.memory import MemoryFactType

_ERROR_EXTRACT_PROMPT = """你是一个智能记忆抽取器。请根据以下发生的工具调用错误和用户输入，提取出一条简短、深刻的“教训（Error Lesson）”。
这条教训应该能指导未来的 Agent 避免犯同样的错误。

用户当时的输入：
{user_input}

发生错误的工具调用记录：
{error_calls_text}

请根据上面的错误细节，提炼出有价值的教训事实。
要求：
1. 语言简练，直击核心（不超过 100 字）。
2. 使用客观、普适的规则陈述，避免包含临时性细节，确保教训可复用于类似场景。
3. 事实类型（fact_type）必须是 "error_lesson"。
4. 重要性评分（importance）在 0.8 到 1.0 之间。

必须输出如下格式的 JSON，不要包含任何其他多余文本：
{{
  "facts": [
    {{
      "content": "教训内容",
      "fact_type": "error_lesson",
      "importance": 0.9
    }}
  ]
}}"""

_TURN_EXTRACT_PROMPT = """你是一个智能记忆抽取器。请分析下面这段单轮对话，仅提取具有长期复用价值的高价值信息。

可提取的类型：
1. 用户个人信息或持久性偏好 → fact_type: "preference"
2. 用户对 AI 错误认知的纠正 → fact_type: "knowledge"

判断标准：该信息在未来的对话中是否仍然有用？如果只对当前这一次操作有意义，则不提取。

不要提取一次性的操作请求、具体的查询内容、临时性细节或日常寒暄。
大多数普通对话不包含高价值信息，此时请返回空数组。

待分析的对话：
{history_text}

必须输出如下格式的 JSON：
{{
  "facts": [
    {{
      "content": "事实内容",
      "fact_type": "preference|knowledge",
      "importance": 0.9
    }}
  ]
}}"""

_BATCH_EXTRACT_PROMPT = """你是一个智能记忆抽取器。请分析下面这段历史对话，从中提取出对未来有长期指导价值的"记忆事实（Facts）"。

你需要关注的事实类型包括：
1. "env_constraint"（环境约束）：操作系统、目录结构、服务配置、API 限制等环境信息
2. "preference"（用户偏好）：用户的个人信息、交互风格偏好、工具选择等持久性偏好
3. "knowledge"（长期知识）：用户分享或确认的业务事实、固定配置、项目约定等

⚠ 以下高价值信息必须优先抽取（importance ≥ 0.85）：
- 用户身份信息（名字、职业、年龄等）→ 归为 "preference"
- 明确指令（用户要求 AI 以后如何行为）→ 归为 "preference"
- 纠正反馈（用户纠正了 AI 的错误认知）→ 归为 "knowledge"

不要提取纯粹的寒暄（如"你好"、"谢谢"）或无长期价值的临时性信息。
如果这段对话没有包含任何有长期保存价值的事实，请返回空数组。

待分析的历史对话：
{history_text}

请返回提炼后的 facts 数组。
要求：
1. 每条事实内容必须简洁、准确，具有长效指导意义（不超过 100 字）。
2. 重要性评分（importance）：高价值信息（身份/指令/纠正）设为 0.85-0.95，一般事实设为 0.4-0.8。

必须输出如下格式的 JSON，不要包含任何其他多余文本：
{{
  "facts": [
    {{
      "content": "事实内容",
      "fact_type": "env_constraint|preference|knowledge",
      "importance": 0.7
    }}
  ]
}}"""


class MemoryExtractor:
    """L2 记忆事实抽取器类"""

    @staticmethod
    def extract_from_error_calls(user_input: str, error_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        从工具调用错误中立即提取教训

        :param user_input: 当前用户的输入
        :param error_calls: 发生错误的工具调用记录列表
        :return: 抽取的记忆 facts 列表
        """
        if not error_calls:
            return []

        # 格式化错误调用记录
        formatted_calls = []
        for i, call in enumerate(error_calls, 1):
            formatted_calls.append(
                f"错误 {i}:\n"
                f"- 工具名: {call.get('name')}\n"
                f"- 类型: {call.get('kind')}\n"
                f"- 参数: {json.dumps(call.get('arguments'), ensure_ascii=False)}\n"
                f"- 报错信息: {call.get('error')}"
            )
        error_calls_text = "\n\n".join(formatted_calls)

        prompt = _ERROR_EXTRACT_PROMPT.format(
            user_input=user_input,
            error_calls_text=error_calls_text
        )

        try:
            llm = get_llm_fast()
            response = llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # 使用低采样温度，确保确定性
                response_format={"type": "json_object"},
                max_tokens=400
            )
            data = json.loads(response)
            facts = data.get("facts", [])
            logger.info("[Memory Extractor] 从工具错误中抽取出 {} 条教训", len(facts))
            return facts
        except Exception as e:
            logger.exception("[Memory Extractor] 提取工具错误教训时失败: {}", e)
            return []

    @staticmethod
    def extract_from_turn(user_input: str, assistant_answer: str) -> List[Dict[str, Any]]:
        """
        从单轮对话中即时抽取高价值事实（轻量版，不依赖 ORM 对象）。

        每轮对话结束后异步调用，确保用户身份、明确指令、纠正反馈等
        高价值信息能立即存入 L2 长期记忆，无需等待摘要压缩。

        :param user_input: 用户本轮输入
        :param assistant_answer: AI 本轮回复
        :return: 抽取的记忆 facts 列表
        """
        if not user_input:
            return []

        history_text = f"[用户] {user_input}\n[AI助手] {assistant_answer[:300]}"
        prompt = _TURN_EXTRACT_PROMPT.format(history_text=history_text)

        try:
            llm = get_llm_fast()
            response = llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=400
            )
            data = json.loads(response)
            facts = data.get("facts", [])
            logger.info("[Memory Extractor] 从当前轮对话即时抽取出 {} 条事实", len(facts))
            return facts
        except Exception as e:
            logger.exception("[Memory Extractor] 即时抽取事实失败: {}", e)
            return []

    @staticmethod
    def extract_from_history(messages: List[Any]) -> List[Dict[str, Any]]:
        """
        从历史对话记录中批量提取事实（用户偏好、环境约束、业务知识）

        :param messages: 即将压缩的 ChatMessage 列表
        :return: 抽取的记忆 facts 列表
        """
        if not messages:
            return []

        # 将对话历史转化为易读文本
        history_lines = []
        for m in messages:
            role_label = "用户" if m.role.value == "user" else "AI助手"
            content_preview = m.content[:300] + ("..." if len(m.content) > 300 else "")
            history_lines.append(f"[{role_label}] {content_preview}")
        history_text = "\n".join(history_lines)

        prompt = _BATCH_EXTRACT_PROMPT.format(history_text=history_text)

        try:
            llm = get_llm_fast()
            response = llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
                max_tokens=800
            )
            data = json.loads(response)
            facts = data.get("facts", [])
            logger.info("[Memory Extractor] 从对话历史中批量抽取出 {} 条事实", len(facts))
            return facts
        except Exception as e:
            logger.exception("[Memory Extractor] 从对话历史批量提取事实时失败: {}", e)
            return []
