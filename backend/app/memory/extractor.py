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
2. 使用客观、普适的规则陈述，例如：“在 Windows 环境下运行 shell 命令时，应使用双引号而非单引号包裹参数。” 或 “由于沙箱权限限制，不要直接向 backend/ 目录写入文件，应当写到 data/ 目录。”
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

_BATCH_EXTRACT_PROMPT = """你是一个智能记忆抽取器。请分析下面这段即将归档的历史对话，从中提取出对未来有长期指导价值的“记忆事实（Facts）”。

你需要关注的事实类型包括：
1. "env_constraint"（环境约束）：如操作系统、特定目录路径、API限制等，例如：“用户的电脑是 Windows 系统，需提供 Powershell 兼容脚本。”
2. "preference"（用户偏好）：如用户喜欢的编程语言、交互风格等，例如：“用户更喜欢使用 Python 编写自动化脚本。”
3. "knowledge"（长期知识）：用户分享的或共同确认的关键业务事实或固定逻辑，例如：“本项目的服务端部署在 8000 端口，前端部署在 5173 端口。”

不要提取无意义、临时性或日常问候的信息（如“用户说了你好”）。
如果这段对话没有包含任何有长期保存价值的事实，请返回空数组。

待分析的历史对话：
{history_text}

请返回提炼后的 facts 数组。
要求：
1. 每条事实内容必须简洁、准确，具有长效指导意义（不超过 100 字）。
2. 重要性评分（importance）根据事实的价值设定在 0.4 到 0.9 之间。

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
