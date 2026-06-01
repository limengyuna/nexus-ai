"""
系统预置的结构化档案 (Profile Slots) 槽位定义。
"""

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
        "slot_key": "agent.detail_level",
        "slot_type": "agent",
        "value_type": "enum",
        "allowed_values": ["low", "medium", "high"],
        "description": "回答的详细程度",
    },
    {
        "slot_key": "agent.autonomy_level",
        "slot_type": "agent",
        "value_type": "enum",
        "allowed_values": ["conservative", "ask_first", "proactive"],
        "description": "代理的自主执行水平",
    },
    {
        "slot_key": "agent.clarification_preference",
        "slot_type": "agent",
        "value_type": "enum",
        "allowed_values": ["ask_first", "assume_and_explain"],
        "description": "信息不足时偏好先问还是先给假设方案",
    },
    # knowledge
    {
        "slot_key": "knowledge.preferred_citation_style",
        "slot_type": "knowledge",
        "value_type": "string",
        "description": "回答是否需要引用来源，及引用风格",
    },
    {
        "slot_key": "knowledge.answer_grounding_requirement",
        "slot_type": "knowledge",
        "value_type": "boolean",
        "description": "是否要求“无依据不回答”",
    },
    # tool
    {
        "slot_key": "tool.approval_sensitivity",
        "slot_type": "tool",
        "value_type": "string",
        "description": "高风险工具是否必须人工确认的规则",
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
