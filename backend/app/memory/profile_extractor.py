"""
结构化用户档案（Profile Slot）抽取器

负责从单轮对话中，使用 LLM 自动提取出符合槽位白名单的用户长期偏好、约束或高价值候选偏好。
"""
import json
from typing import Any, Dict, List
from loguru import logger

from app.agent.llm import get_llm_fast


_PROFILE_EXTRACT_PROMPT = """你是一个智能用户偏好与长期约束提取器。你的任务是分析当前轮次的对话，提取出能够反映用户【长期稳定偏好、个人工作画像、工具调用安全约束、输出格式习惯、业务领域】的信息。

【提取原则】
1. 仅限长期偏好：必须是长久、跨会话生效的信息（如：偏好简洁、操作系统是 Windows、主要关注金融文档、任何删除操作必须审批）。
2. 过滤临时性指令：严禁提取仅对当前对话或当前具体任务有效的短期指令与参数（如：“帮我查下这份文件”、“写一段快速排序代码”、“今天天气怎么样”）。
3. 宁缺毋滥：只有当用户在对话中明确表述或通过行为展现出长期稳定的习惯时才提取。如果本轮对话没有任何长期偏好信息，返回空数组的 JSON。
4. 冲突覆盖：如果提取的信息修正了用户已有的偏好，请使用最新的表达。

【系统可用槽位（Slot）白名单】
系统仅允许将偏好映射到以下预定义的 Slot 中：
{slot_definitions}

【当前用户已生效的偏好】
{current_profile_text}

【当前轮对话】
用户：{user_input}
助手：{assistant_answer}

【输出格式要求】
你必须且只能输出如下格式的合法 JSON 对象（不要带有 markdown 标记或多余的解释文字，如果是空结果则 updates 和 candidates 为空列表）：
{{
  "updates": [
    {{
      "slot_key": "必须在白名单中的 slot_key",
      "slot_value": "提取的具体值。注意：如果是 enum 类型，必须从 allowed_values 中选择；如果是 list 类型，输出为 JSON 数组；其他为 string",
      "confidence": 0.0到1.0的置信度评分,
      "source": "explicit"（用户明确说了）或 "inferred"（根据用户提问隐含推断出的长期倾向）,
      "reason": "提取此设定的简短理由（中文）"
    }}
  ],
  "candidates": [
    {{
      "candidate_text": "在槽位白名单外、但具有高价值的个人信息或长期偏好事实",
      "suggested_slot_key": "建议的 slot_key 键名（若有类似倾向，可选）",
      "suggested_value": "建议的值（可选）",
      "confidence": 0.0到1.0的置信度评分,
      "reason": "提取为候选的理由（中文）"
    }}
  ]
}}
"""


class ProfileExtractor:
    """结构化 Profile 抽取器"""

    @staticmethod
    def extract(
        user_input: str,
        assistant_answer: str,
        slots_definitions: List[Dict[str, Any]],
        current_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        从单轮对话中抽取偏好 slot 的更新及候选偏好。
        
        :param user_input: 用户本轮输入
        :param assistant_answer: 助手本轮回复
        :param slots_definitions: 系统当前启用的 slot 白名单字典列表
        :param current_profile: 用户已有的偏好映射字典 {slot_key: slot_value}
        :return: 包含 updates 和 candidates 的字典
        """
        if not user_input:
            return {"updates": [], "candidates": []}

        # 1. 格式化 Slot 白名单定义
        defs_lines = []
        for s in slots_definitions:
            allowed = f" (允许的值: {s.get('allowed_values')})" if s.get("allowed_values") else ""
            defs_lines.append(f"- {s['slot_key']} (类型: {s['value_type']}): {s.get('description', '')}{allowed}")
        slot_definitions_text = "\n".join(defs_lines)

        # 2. 格式化当前用户已有偏好
        if not current_profile:
            current_profile_text = "(暂无偏好设置)"
        else:
            profile_lines = []
            for k, v in current_profile.items():
                profile_lines.append(f"- {k}: {json.dumps(v, ensure_ascii=False)}")
            current_profile_text = "\n".join(profile_lines)

        # 3. 组装 Prompt
        prompt = _PROFILE_EXTRACT_PROMPT.format(
            slot_definitions=slot_definitions_text,
            current_profile_text=current_profile_text,
            user_input=user_input,
            assistant_answer=assistant_answer[:400]  # 取前400字符即可，减少无意义上下文
        )

        try:
            llm = get_llm_fast()
            response = llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # 确保稳定性
                response_format={"type": "json_object"},
                max_tokens=600
            )
            data = json.loads(response)
            updates = data.get("updates", [])
            candidates = data.get("candidates", [])
            logger.info("[Profile Extractor] 从当前轮对话中提取到 {} 条 Slot 更新，{} 条候选", len(updates), len(candidates))
            return {"updates": updates, "candidates": candidates}
        except Exception as e:
            logger.exception("[Profile Extractor] 提取结构化偏好失败: {}", e)
            return {"updates": [], "candidates": []}
