"""
Router Agent 节点

职责：根据用户输入识别意图，输出 intent 标签供主图条件路由：
- "rag":      需要查知识库回答（用户问题涉及上传的文档）
- "tool":     需要调用工具或 Skill（旅行规划、计算等）
- "chitchat": 闲聊或常识问答，不需要 RAG 也不需要工具

决策流程：
1. 调 LLM（JSON 模式）做意图分类 + 推荐 Skill（recommended_skill）
2. 若推荐了 Skill 且该 Skill 真实存在，写入 matched_skill 供 Tool Agent 强制执行
3. 把决策原因记入 route_reason，便于"思考过程"展示
"""
import json
import time
from typing import Any, Dict

from loguru import logger

from app.agent.llm import get_llm_fast
from app.agent.skills import skill_registry
from app.agent.state import AgentState, append_trace

# 可路由的意图标签
ROUTE_RAG = "rag"
ROUTE_TOOL = "tool"
ROUTE_CHITCHAT = "chitchat"


_ROUTER_SYSTEM_PROMPT = """你是 NexusAI 平台的意图路由器。把用户输入分类到下列之一：

1. "rag"      - 用户在问已上传到知识库里的文档/资料内容
2. "tool"     - 用户需要借助工具或外部服务来完成任务（搜索、计算、访问代码仓库、调用 API 等）
               ⚠ 涉及实时/时效性信息（当前时间、天气、新闻、股价、赛事比分等）也必须选 "tool"
3. "chitchat" - 闲聊、问候、一般常识问答（不涉及实时数据的日常对话）

当前可用技能/服务（若用户意图明确匹配某个技能，选 "tool" 并在 recommended_skill 写上技能名）：
{capabilities}

输出严格的 JSON 格式：
{{"intent": "rag|tool|chitchat", "reason": "简短理由（中文）", "recommended_skill": "技能名或null"}}

规则：
- recommended_skill 仅在用户明确要求执行某个技能的核心能力时才填写（如用户要求做调研、写邮件、总结文档等动作）
- 用户只是在对话中附带提及相关词汇但实际意图是其他操作时，不要填
- 不确定时填 null，让 Tool Agent 自行决策

只输出 JSON，不要其他任何文字。"""


def _get_mcp_server_names(user_id: int | None) -> list[str]:
    """
    轻量级获取用户已配置的 MCP 服务器名称列表。
    只查 DB 配置表，不拉取具体工具列表，保持 Router 轻量。
    """
    if user_id is None:
        return []
    try:
        from app.core.database import SessionLocal
        from app.models.mcp_server import MCPServerConfig

        db = SessionLocal()
        try:
            configs = (
                db.query(MCPServerConfig.name)
                .filter(
                    MCPServerConfig.created_by == user_id,
                    MCPServerConfig.is_active.is_(True),
                )
                .all()
            )
            return [c.name for c in configs]
        finally:
            db.close()
    except Exception as e:
        logger.warning("[Router] 加载 MCP 服务器名称失败: {}", e)
        return []


def _build_capabilities_brief(user_id: int | None) -> str:
    """
    统一构建“可用能力”描述，合并 Skill + MCP 服务器名称。
    保持简洁，让 Router LLM 知道“tool 能做什么”即可。
    """
    lines = []
    # Skill（内存读取，零开销）
    for s in skill_registry.to_choices_for_router():
        lines.append(f"- [技能] {s['name']}: {s['description']}")
    # MCP 服务器名称（轻量 DB 查询）
    mcp_names = _get_mcp_server_names(user_id)
    for name in mcp_names:
        lines.append(f"- [外部服务] {name}")
    return "\n".join(lines) if lines else "(暂无)"


def router_node(state: AgentState) -> Dict[str, Any]:
    """Router Agent：意图识别"""
    started_at = time.time()
    user_input = state.get("user_input", "")
    has_kb = state.get("kb_id") is not None

    # ---------- LLM 意图分类（同时推荐 Skill） ----------
    capabilities = _build_capabilities_brief(state.get("user_id"))
    system_prompt = _ROUTER_SYSTEM_PROMPT.format(capabilities=capabilities)

    # 构建 LLM 消息：上下文由 context_prep 节点统一注入到 state.messages
    router_messages = [
        {"role": "system", "content": system_prompt},
        *state.get("context_messages", []),  # 包含对话历史 + 当前用户输入
    ]

    llm = get_llm_fast()
    intent = ROUTE_CHITCHAT
    reason = ""
    recommended_skill = None
    node_tokens = 0
    # DeepSeek Flash 偶尔返回空内容，重试一次提高稳定性
    for attempt in range(2):
        try:
            raw, usage = llm.complete_counted(
                messages=router_messages,
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=200,
            )
            node_tokens += usage.get("total_tokens", 0)
            if not raw or not raw.strip():
                logger.warning("[Router] LLM 返回空内容（第 {} 次），重试", attempt + 1)
                continue
            parsed = json.loads(raw)
            intent = parsed.get("intent", ROUTE_CHITCHAT).lower()
            reason = parsed.get("reason", "")
            recommended_skill = parsed.get("recommended_skill") or None
            break  # 解析成功，跳出重试
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("[Router] LLM 路由失败（第 {} 次）: {}", attempt + 1, e)
            if attempt == 1:
                # 两次都失败，降级到 chitchat
                intent = ROUTE_CHITCHAT
                reason = f"LLM 路由失败({e})，降级闲聊"

    # ---------- 后处理：若意图为 rag 但没有绑定知识库，降级到 chitchat ----------
    if intent == ROUTE_RAG and not has_kb:
        logger.info("[Router] 意图=rag 但未绑定 kb，降级到 chitchat")
        intent = ROUTE_CHITCHAT
        reason = "无关联知识库，降级闲聊"

    # 兜底校验
    if intent not in {ROUTE_RAG, ROUTE_TOOL, ROUTE_CHITCHAT}:
        logger.warning("[Router] 收到未知 intent: {}, 降级到 chitchat", intent)
        intent = ROUTE_CHITCHAT

    # ---------- 后处理：关键词预匹配覆盖 intent ----------
    # 当 LLM 判断为 rag 时，用关键词匹配检查是否命中了 Skill（如 document_summarizer）
    # 如果命中且该 Skill 允许在有 KB 时触发，覆盖 intent 为 tool
    matched_skill_name = None
    if intent == ROUTE_RAG and has_kb:
        matched = skill_registry.match_by_keywords(user_input, has_kb=True)
        if matched:
            logger.info("[Router] 关键词预匹配命中 Skill '{}', 覆盖 intent: rag → tool", matched.name)
            intent = ROUTE_TOOL
            matched_skill_name = matched.name
            reason = f"关键词匹配覆盖：{reason} → 触发技能 {matched.name}"

    # 验证 LLM 推荐的 recommended_skill 是否真实存在（仅在未被关键词覆盖时）
    if matched_skill_name is None and intent == ROUTE_TOOL and recommended_skill:
        from app.agent.skills import get_skill
        if get_skill(recommended_skill) is not None:
            matched_skill_name = recommended_skill
            logger.info("[Router] LLM 推荐 Skill: {}", recommended_skill)
        else:
            logger.warning("[Router] LLM 推荐的 Skill '{}' 不存在，忽略", recommended_skill)

    # ---------- 后处理：操作关键词检测 ----------
    _POST_ACTION_KEYWORDS = ["写入", "保存", "存入", "导出", "写到", "写进", "存到", "存进", "发送", "发给"]
    has_action_keywords = any(kw in user_input for kw in _POST_ACTION_KEYWORDS)

    # 有环图：当 intent=rag 且有操作关键词时，RAG Agent 执行完后继续路由到 Tool Agent
    needs_post_action = False
    if intent == ROUTE_RAG and has_action_keywords:
        needs_post_action = True
        logger.info("[Router] 检测到操作关键词，设置 needs_post_action=True")

    # 复合请求检测：当同时有 matched_skill 和操作关键词时，
    # 取消强制 Skill，让 FC 循环自主处理复合请求（先调 Skill 再调 MCP 工具）
    if matched_skill_name and has_action_keywords:
        logger.info("[Router] 复合请求（{} + 操作），取消强制 Skill，走 FC 循环", matched_skill_name)
        matched_skill_name = None

    logger.info("[Router] LLM 决策 → {} | 理由: {} | skill: {} | post_action: {}",
                intent, reason, matched_skill_name, needs_post_action)

    result = {
        "intent": intent,
        "route_reason": reason,
        "needs_post_action": needs_post_action,
        "total_tokens": state.get("total_tokens", 0) + node_tokens,
        "execution_trace": append_trace(
            state, "router", started_at,
            input_summary={"user_input": user_input[:80], "has_kb": has_kb},
            output_summary={"intent": intent, "reason": reason, "skill": matched_skill_name,
                            "needs_post_action": needs_post_action, "tokens": node_tokens},
        ),
    }
    if matched_skill_name:
        result["matched_skill"] = matched_skill_name
    return result
