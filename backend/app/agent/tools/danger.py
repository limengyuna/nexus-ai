"""
危险工具识别

判断某个工具调用是否需要"用户审批"才能执行。

设计哲学（与方案 C 配套）：
- 内部 Tool（项目自己的）：白名单显式标记，默认安全（calculator/web_search/rag_search/weather 等纯查询）
- Skill（项目自己的）：默认安全（受控代码）
- MCP Tool（用户动态配置的外部工具）：**默认危险**，因为我们无法审计其源码
  - 原因：MCP 工具是用户在前端动态接入的（写文件、发邮件、API 调用、shell 执行……），
    其副作用对 Agent 不透明。一旦 LLM 误调用就会真实改变外部状态。
  - 显式白名单（safe_mcp_tool_names）可豁免：例如纯查询型 MCP（搜索类）可加入白名单。

返回值约定：
- True  → 执行前必须 interrupt() 暂停，等待用户审批
- False → 直接执行
"""
from typing import Optional

# 内部 Tool 的安全白名单（这些是 BaseTool 的子类名/工具 name）
# 凡是项目内部已知"无副作用"的，加到这里
# 命名规范：尽量列出工具的"语义关键词"，下文使用子串匹配以兼容 get_weather / weather_query 等命名
_SAFE_INTERNAL_TOOLS = {
    "calculator",       # 纯计算
    "weather",          # 只读 API（兼容 get_weather）
    "web_search",       # 只读搜索（兼容 web_search、search_web）
    "rag_search",       # 只读检索
    "search",           # 任何搜索类
    "query",            # 查询类
    "get_",             # 任何 get_xxx 通常是只读
    "list_",            # 任何 list_xxx 通常是只读
    "fetch_",           # 任何 fetch_xxx 通常是只读
    "read_",            # 任何 read_xxx 通常是只读
}

# MCP Tool 中显式标记为安全的工具名（前缀 + 完整名匹配）
# 例如 "tavily_search" 这类查询型工具可以预先豁免
_SAFE_MCP_TOOL_KEYWORDS = {
    "search", "query", "list", "get", "read", "fetch", "describe",
    "lookup", "find", "retrieve",
}

# MCP Tool 中明确危险的关键词（即便用户加了白名单也建议二次确认）
# 这里仅做日志强化，不影响判断结果（判断主入口已经默认 MCP=危险）
_HIGH_RISK_KEYWORDS = {
    "write", "create", "delete", "remove", "update", "execute",
    "run", "send", "publish", "post", "patch", "drop", "truncate",
    "kill", "shutdown", "restart", "deploy",
}


def is_dangerous_tool(
    tool_name: str,
    tool_kind: str,
    *,
    safe_mcp_whitelist: Optional[set] = None,
) -> bool:
    """
    判断工具调用是否需要审批。

    :param tool_name: 工具名（OpenAI Function Calling 中的 name）
    :param tool_kind: 工具类型: "internal" / "mcp" / "skill"
    :param safe_mcp_whitelist: 用户配置的 MCP 安全白名单（可选，按工具名精确匹配）
    :return: True 表示危险（需审批），False 表示安全（直接执行）
    """
    if not tool_name:
        return False

    name_lower = tool_name.lower()

    # ---------- 内部 Tool ----------
    if tool_kind == "internal":
        # 白名单关键字命中 → 安全（子串匹配兼容 get_weather / web_search 等命名）
        if any(kw in name_lower for kw in _SAFE_INTERNAL_TOOLS):
            return False
        # 高危关键词命中 → 危险
        if any(kw in name_lower for kw in _HIGH_RISK_KEYWORDS):
            return True
        # 默认：内部工具是项目自己写的，未命中关键字时按"安全"放行（避免误伤）
        return False

    # ---------- Skill（项目自己写的，受控）----------
    if tool_kind == "skill":
        return False

    # ---------- MCP Tool（默认危险，谨慎放行）----------
    if tool_kind == "mcp":
        # 用户显式白名单豁免
        if safe_mcp_whitelist and tool_name in safe_mcp_whitelist:
            return False
        # 启发式：纯查询关键词（list_* / get_* / search_* / read_*）→ 可豁免
        # 但若同时含高危关键词（如 write_after_read），则仍判为危险
        has_safe_kw = any(kw in name_lower for kw in _SAFE_MCP_TOOL_KEYWORDS)
        has_risk_kw = any(kw in name_lower for kw in _HIGH_RISK_KEYWORDS)
        if has_safe_kw and not has_risk_kw:
            return False
        # 默认：MCP 工具一律视为危险
        return True

    # 未知类型 → 保守判断为危险
    return True


def build_approval_payload(
    tool_name: str,
    tool_kind: str,
    arguments: dict,
    description: str = "",
) -> dict:
    """
    构造发给前端审批 UI 的载荷（必须 JSON-serializable）。

    前端拿到后展示一个审批卡片：
    - 标题：将要调用 XXX 工具
    - 详情：参数预览
    - 按钮：批准 / 拒绝
    """
    return {
        "type": "tool_approval",
        "tool_name": tool_name,
        "tool_kind": tool_kind,
        "description": description,
        "arguments": arguments,
        "message": f"是否允许 Agent 调用工具「{tool_name}」？",
    }
