"""
系统预置的结构化档案 (Profile Slots) 槽位定义。
"""

DEPRECATED_MEMORY_SLOT_KEYS = {
    "agent.autonomy_level",
    "knowledge.answer_grounding_requirement",
    "tool.approval_sensitivity",
    "agent.detail_level",                    # 与 response_style 语义重叠，已合并
    "knowledge.preferred_citation_style",     # RAG system prompt 已覆盖引用格式
}

DEFAULT_MEMORY_SLOTS = [
    # profile
    {
        "slot_key": "profile.role",
        "slot_type": "profile",
        "value_type": "string",
        "description": "用户在组织或工作中的角色",
    },
    {
        "slot_key": "profile.primary_language",
        "slot_type": "profile",
        "value_type": "string",
        "description": "偏好的交流语言",
    },
    # agent
    {
        "slot_key": "agent.response_style",
        "slot_type": "agent",
        "value_type": "enum",
        "allowed_values": ["concise", "detailed", "step_by_step", "formal"],
        "description": "用户偏好的回答风格",
    },

    {
        "slot_key": "agent.clarification_preference",
        "slot_type": "agent",
        "value_type": "enum",
        "allowed_values": ["ask_first", "assume_and_explain"],
        "description": "信息不足时偏好先问还是先给假设方案",
    },

    # output
    {
        "slot_key": "output.default_format",
        "slot_type": "output",
        "value_type": "enum",
        "allowed_values": ["paragraph", "list", "table", "markdown", "json"],
        "description": "偏好的默认输出格式",
    },
    # domain
    {
        "slot_key": "domain.business_domain",
        "slot_type": "domain",
        "value_type": "string",
        "description": "用户长期关注的业务领域",
    },
    # constraint
    {
        "slot_key": "constraint.must_follow",
        "slot_type": "constraint",
        "value_type": "string",
        "description": "必须遵守的长期规则",
    },
    {
        "slot_key": "constraint.do_not_do",
        "slot_type": "constraint",
        "value_type": "string",
        "description": "用户明确禁止的行为",
    },
    {
        "slot_key": "constraint.data_sensitivity",
        "slot_type": "constraint",
        "value_type": "string",
        "description": "敏感数据处理偏好",
    },
]
