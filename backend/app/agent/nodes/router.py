"""
Router Agent 节点

职责：根据用户输入识别意图，输出 intent 标签供主图条件路由：
- "rag":      需要查知识库回答（用户问题涉及上传的文档）
- "tool":     需要调用工具或 Skill（旅行规划、计算等）
- "chitchat": 闲聊或常识问答，不需要 RAG 也不需要工具

决策流程：
1. 先用 Skill 注册中心的关键词预匹配（极快）
2. 若无关键词命中，再调 LLM 用 JSON 模式做精确意图分类
3. 把决策原因记入 route_reason，便于"思考过程"展示
"""
import json
import time
from typing import Any, Dict

from loguru import logger

from app.agent.llm import get_llm
from app.agent.skills import skill_registry
from app.agent.state import AgentState, append_trace

# 可路由的意图标签
ROUTE_RAG = "rag"
ROUTE_TOOL = "tool"
ROUTE_CHITCHAT = "chitchat"


_ROUTER_SYSTEM_PROMPT = """你是 NexusAI 平台的意图路由器。把用户输入分类到下列之一：

1. "rag"      - 用户在问知识库里的文档相关问题（如：项目架构、文档内容、上传过的资料）
2. "tool"     - 用户需要调用工具或技能（如：查天气、算数学、查实时数据、旅行规划）
3. "chitchat" - 闲聊、问候、一般常识问答

可用技能（如果意图属于这些技能范畴，请选 "tool"）：
{skills}

输出严格的 JSON 格式：
{{"intent": "rag|tool|chitchat", "reason": "简短理由（中文）"}}

只输出 JSON，不要其他任何文字。"""


def router_node(state: AgentState) -> Dict[str, Any]:
    """Router Agent：意图识别"""
    started_at = time.time()
    user_input = state.get("user_input", "")
    has_kb = state.get("kb_id") is not None

    # ---------- 阶段 1：关键词预匹配 Skill ----------
    # 仅在【未绑定知识库】的场景下走捷径；
    # 一旦会话关联了 KB，必须让 LLM 精确判断，避免"向量数据库"中"数据"被 data_analyst 误命中
    matched_skill = None
    if not has_kb:
        matched_skill = skill_registry.match_by_keywords(user_input)
    if matched_skill is not None:
        intent = ROUTE_TOOL
        reason = f"关键词匹配到技能 [{matched_skill.name}]"
        logger.info("[Router] 关键词命中 → {} (skill={})", intent, matched_skill.name)
        return {
            "intent": intent,
            "route_reason": reason,
            "execution_trace": append_trace(
                state, "router", started_at,
                input_summary={"user_input": user_input[:80]},
                output_summary={"intent": intent, "matched_skill": matched_skill.name},
            ),
        }

    # ---------- 阶段 2：LLM 精确分类 ----------
    skills_brief = "\n".join(
        f"- {s['name']}: {s['description']}"
        for s in skill_registry.to_choices_for_router()
    )
    system_prompt = _ROUTER_SYSTEM_PROMPT.format(skills=skills_brief or "(暂无可用技能)")

    # 构建 LLM 消息：注入对话历史上下文，帮助 Router 理解指代性表述（如“这个项目”）
    summary = state.get("summary", "")
    router_messages = [
        {"role": "system", "content": system_prompt},
    ]
    if summary:
        router_messages.append({
            "role": "system",
            "content": f"以下是之前的对话上下文，请结合上下文判断用户意图：\n{summary}",
        })
    router_messages.append({"role": "user", "content": user_input})

    llm = get_llm()
    try:
        raw = llm.complete(
            messages=router_messages,
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        parsed = json.loads(raw)
        intent = parsed.get("intent", ROUTE_CHITCHAT).lower()
        reason = parsed.get("reason", "")
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("[Router] LLM 路由失败，降级到 chitchat: {}", e)
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

    logger.info("[Router] LLM 决策 → {} | 理由: {}", intent, reason)

    return {
        "intent": intent,
        "route_reason": reason,
        "execution_trace": append_trace(
            state, "router", started_at,
            input_summary={"user_input": user_input[:80], "has_kb": has_kb},
            output_summary={"intent": intent, "reason": reason},
        ),
    }
