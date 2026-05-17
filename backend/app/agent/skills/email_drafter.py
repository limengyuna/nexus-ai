"""
邮件起草技能（Skill）—— 纯 LLM 多步编排示例

工作流（与其他 Skill 形成对比，0 Tool 调用）：
1. Step 1: LLM 从用户口语化需求中抽取"邮件元素"
   → 收件人角色、邮件目的、推荐语气（正式/友好/严肃）、关键信息列表
2. Step 2: LLM 基于元素生成专业邮件（主题行 + 正文 + Markdown 格式）

亮点：
- 演示 Skill 不一定要有 Tool —— 多步 Prompt 编排也是 Skill
- 第一步输出 JSON 是"结构化思考"，第二步基于结构化结果生成
  这种「先抽取/规划，再生成」是业界写复杂 prompt 的标准做法
- 与其他 Skill 对比：
    travel_planner       1 LLM + 1 Tool   单 Tool 增强
    data_analyst         2 LLM + 1 Tool   LLM-Tool-LLM 三明治
    document_summarizer  2 LLM + N Tool   multi-query RAG
    research_assistant   2 LLM + N Tool   多源综合（web+RAG）
    email_drafter        2 LLM + 0 Tool   纯 LLM 链式推理  ← 这个
"""
import json
from typing import Any, Dict, Optional

from loguru import logger

from app.agent.skills.registry import BaseSkill, register_skill


@register_skill
class EmailDrafterSkill(BaseSkill):
    """邮件起草：从口语化需求 → 专业邮件"""

    name = "email_drafter"
    description = (
        "把用户口语化的需求转写成专业邮件。先用 LLM 抽取"
        "收件人/目的/语气/关键信息，再生成带主题行的完整邮件正文。"
        "适合「帮我写封请假邮件」「起草一封跟客户致歉的信」等场景。"
    )
    required_tools: list = []  # 纯 LLM 编排，无需 Tool
    trigger_keywords = [
        "邮件", "起草", "写封信", "写邮件", "email", "draft", "回信",
    ]

    def execute(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        # 对话上下文（含用户姓名、历史消息等）
        context_messages = context.get("context_messages", [])
        tool_calls = []

        # ---------- Step 1: LLM 抽取邮件元素 ----------
        elements = self._llm_extract(user_input, context_messages)
        logger.info("[Skill:{}] 抽取的邮件元素: {}", self.name, elements)
        tool_calls.append({
            "name": "llm_extract_elements",
            "kind": "llm",
            "arguments": {"user_input": user_input},
            "result": elements,
        })

        # ---------- Step 2: LLM 基于元素生成邮件 ----------
        email_md = self._llm_compose(user_input, elements, context_messages)
        tool_calls.append({
            "name": "llm_compose_email",
            "kind": "llm",
            "arguments": {"elements": elements},
            "result": f"输出 {len(email_md)} 字符邮件草稿",
        })

        return {
            "answer": email_md,
            "tool_calls": tool_calls,
            "meta": {
                "skill": self.name,
                "tone": elements.get("tone"),
                "recipient_role": elements.get("recipient_role"),
            },
        }

    # ---------- Step 1: 抽取元素 ----------
    def _llm_extract(self, user_input: str, context_messages: list = None) -> Dict[str, Any]:
        """让 LLM 把口语化需求分解为结构化元素"""
        from app.agent.llm import get_llm

        llm = get_llm()
        # 拼接对话历史摘要，让 LLM 感知用户姓名等信息
        history_hint = ""
        if context_messages:
            parts = []
            for msg in context_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    parts.append(f"{role}: {content}")
            if parts:
                history_hint = "\n对话历史（可能含用户姓名等信息）：\n" + "\n".join(parts[-6:]) + "\n"
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是邮件助手。基于用户的口语化需求和对话上下文，抽取邮件的关键元素。\n"
                    "**只输出严格的 JSON 对象**，键固定为：\n"
                    "  - recipient_role: 收件人角色（如「直属上级」「客户」「老师」「合作方」）\n"
                    "  - sender_name: 发件人姓名（从对话历史中提取，找不到则留空）\n"
                    "  - sender_role: 发件人角色（如「员工」「学生」「乙方」，找不到就写「我」）\n"
                    "  - purpose: 邮件目的（一句话，如「请假申请」「项目延期说明」）\n"
                    "  - tone: 推荐语气（取值：formal / friendly / apologetic / urgent / casual）\n"
                    "  - key_points: 关键信息列表（数组，按邮件应该呈现的顺序）\n"
                    "  - language: 推断的语言（zh / en）\n"
                    "不要任何解释，不要 markdown 代码块包裹。"
                ),
            },
            {
                "role": "user",
                "content": f"{history_hint}用户需求：{user_input}",
            },
        ]
        raw = llm.complete(messages=prompt, temperature=0.2, max_tokens=500)
        # 尽力解析 JSON
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                obj = json.loads(raw[start : end + 1])
                if isinstance(obj, dict):
                    return obj
        except Exception as e:
            logger.warning("[Skill:{}] 元素 JSON 解析失败: {}", self.name, e)
        # 兜底：返回最简结构
        return {
            "recipient_role": "收件人",
            "sender_role": "我",
            "purpose": user_input,
            "tone": "formal",
            "key_points": [user_input],
            "language": "zh",
        }

    # ---------- Step 2: 生成邮件 ----------
    def _llm_compose(self, user_input: str, elements: Dict[str, Any], context_messages: list = None) -> str:
        """基于结构化元素生成专业邮件"""
        from app.agent.llm import get_llm

        # 把语气映射为人类可读描述（让 LLM 更准确执行）
        tone_desc = {
            "formal": "正式且专业，保持距离感",
            "friendly": "友好亲切，但仍保持职业",
            "apologetic": "诚恳致歉，承担责任",
            "urgent": "简明扼要，强调紧迫性",
            "casual": "轻松自然，像朋友间交流",
        }.get(elements.get("tone", "formal"), "正式且专业")

        language = elements.get("language", "zh")
        lang_instruction = (
            "用中文撰写" if language == "zh" else
            "Write in English" if language == "en" else
            "用与用户输入相同的语言撰写"
        )

        llm = get_llm()
        prompt = [
            {
                "role": "system",
                "content": (
                    f"你是专业的商务邮件撰稿人。根据给定的邮件元素生成一封完整邮件。\n"
                    f"**输出格式（严格遵守）**：\n"
                    f"  - 第一行：`**主题：** ...`（用 Markdown 加粗）\n"
                    f"  - 空一行后写正文\n"
                    f"  - 正文包含：称呼 → 开场 → 主体 → 结尾礼貌 → 落款\n"
                    f"**语气要求**：{tone_desc}\n"
                    f"**语言要求**：{lang_instruction}\n"
                    f"**长度**：合理控制，不堆砌废话\n"
                    f"不要任何解释说明，直接输出邮件内容。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## 用户原始需求\n{user_input}\n\n"
                    f"## 提取的邮件元素\n```json\n{json.dumps(elements, ensure_ascii=False, indent=2)}\n```\n\n"
                    "请基于以上元素撰写邮件。"
                ),
            },
        ]
        return llm.complete(messages=prompt, temperature=0.6, max_tokens=800)
