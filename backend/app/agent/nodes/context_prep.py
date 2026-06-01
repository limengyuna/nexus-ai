"""
上下文准备节点（中间件模式）

职责：
- 统一从 state 中读取 summary（对话历史摘要）
- 构造标准化的 messages 列表写入 state.messages
- 后续所有节点直接从 state.messages 读取上下文，无需各自处理

设计原则：
- 单一职责：上下文注入逻辑集中在此，新增节点不需要关心上下文怎么来的
- 参考了 LangGraph Checkpointer 的思想 + 中间件/拦截器模式
"""
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from loguru import logger

from app.agent.state import AgentState, append_trace


def context_prep_node(state: AgentState) -> Dict[str, Any]:
    """
    统一上下文准备节点。

    读取 state.summary（由 chat_service.py 构造，包含摘要 + 最近对话记录），
    并从 L2 语义事实记忆库中检索高度相关的记忆，
    将其转化为标准 messages 格式写入 state.messages，供下游节点直接使用。
    """
    started_at = time.time()

    summary = state.get("summary", "")
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")
    kb_id = state.get("kb_id")

    context_messages = []

    # 注入当前时间（参考 ChatGPT/Claude 做法：在 system 层提供准确时间，杜绝 LLM 编造日期）
    # 明确使用 UTC+8 北京时间，避免 Docker 容器默认 UTC 导致时间差 8 小时
    _CST = timezone(timedelta(hours=8))
    now = datetime.now(_CST)
    time_str = now.strftime("%Y年%m月%d日 %H:%M（%A）")
    context_messages.append({
        "role": "system",
        "content": f"当前时间：{time_str}。如果用户询问实时信息（如当前时间、天气、新闻、股价等），请基于此时间回答或建议使用工具获取最新数据。",
    })

    # 建立数据库连接
    db = None
    retrieved_mems = []
    injected_profile_slots = []
    
    if user_id:
        from app.core.database import SessionLocal
        from app.memory.retriever import MemoryRetriever
        from app.memory.profile_store import MemoryProfileStore
        from app.models.memory_profile import MemorySlot
        from sqlalchemy import select
        
        db = SessionLocal()
        try:
            # 1. 注入结构化用户档案 (Profile Slots)
            profile_values = MemoryProfileStore.get_user_profile(db, user_id)
            slots_map = {s.id: s for s in db.execute(select(MemorySlot)).scalars().all()}
            
            # 基础默认注入的 slots
            active_slot_keys = {
                "profile.primary_language",
                "agent.response_style",
                "agent.detail_level",
            }
            
            # 动态根据用户输入的关键词/意图激活其他 slots，避免过度干扰简单问题
            input_lower = user_input.lower()
            
            # 格式/排版偏好激活
            format_keywords = ["格式", "format", "列表", "表格", "json", "list", "table", "markdown", "排版", "输出", "段落"]
            if any(kw in input_lower for kw in format_keywords):
                active_slot_keys.add("output.default_format")
                
            # 工具/安全确认激活
            tool_keywords = ["执行", "运行", "工具", "审批", "确认", "审核", "敏感", "安全", "run", "tool", "exec", "approve"]
            if any(kw in input_lower for kw in tool_keywords):
                active_slot_keys.add("tool.approval_sensitivity")
                
            # 硬性规则与敏感度约束激活
            constraint_keywords = ["禁止", "严禁", "不允许", "不要", "必须", "绝对", "脱敏", "隐私", "数据", "敏感", "规则", "约束", "rule", "constraint", "must", "never", "privacy", "sensitive"]
            if any(kw in input_lower for kw in constraint_keywords):
                active_slot_keys.add("constraint.must_follow")
                active_slot_keys.add("constraint.do_not_do")
                active_slot_keys.add("constraint.data_sensitivity")
            
            profile_texts = []
            for val in profile_values:
                slot = slots_map.get(val.slot_id)
                if slot and slot.slot_key in active_slot_keys:
                    profile_texts.append(f"- {slot.description}: {val.slot_value}")
                    injected_profile_slots.append({
                        "slot_key": slot.slot_key,
                        "slot_type": slot.slot_type,
                        "slot_value": val.slot_value
                    })
            
            if profile_texts:
                profile_text_block = "\n".join(profile_texts)
                context_messages.append({
                    "role": "system",
                    "content": (
                        "以下是当前用户的结构化偏好与长期约束，请在不违背系统规则的前提下参考：\n"
                        "<user_profile_constraints>\n"
                        f"{profile_text_block}\n"
                        "</user_profile_constraints>\n"
                        "请注意：以上偏好仅在与当前问题相关时参考；若与当前用户明确指令冲突，以当前指令为准。"
                    )
                })
                logger.info("[Context Prep] 成功注入 {} 条 Profile Slots", len(profile_texts))

            # 2. 注入 L2 语义事实库的相关历史事实与教训记忆，并严格过滤已被独立 Profile 接管的 "preference" 事实
            retrieved = MemoryRetriever.retrieve(db, user_input, user_id, kb_id=kb_id, top_k=3)
            relevant_facts = [f for f in retrieved if f.fact_type.value != "preference"]
            
            if relevant_facts:
                facts_text = "\n".join(f"- {f.content}" for f in relevant_facts)
                context_messages.append({
                    "role": "system",
                    "content": f"以下是根据当前问题召回的相关历史记忆，可能包含环境约束、经验教训或长期事实。请结合当前问题谨慎参考；若与用户当前明确表达冲突，以当前表达为准：\n{facts_text}",
                })
                logger.info("[Context Prep] 语义事实记忆成功注入 {} 条事实", len(relevant_facts))
                
                # 转换为 RetrievedMemory 格式以更新到 state 中（供前端和状态管理展示）
                for f in relevant_facts:
                    retrieved_mems.append({
                        "id": f.id,
                        "content": f.content,
                        "fact_type": f.fact_type.value,
                        "importance": f.importance
                    })
        except Exception as e:
            logger.exception("[Context Prep] 从 Profile/L2 检索并注入时发生异常: {}", e)
        finally:
            if db:
                db.close()

    # 注入对话历史上下文（长期记忆 + 最近对话）
    if summary:
        context_messages.append({
            "role": "system",
            "content": f"以下是之前的对话上下文，请结合上下文理解用户意图：\n{summary}",
        })
        logger.info("[Context Prep] 注入对话历史上下文（{}字）", len(summary))

    # 注入当前用户输入
    context_messages.append({"role": "user", "content": user_input})

    logger.info("[Context Prep] 构造 {} 条上下文消息", len(context_messages))

    return {
        "context_messages": context_messages,
        "retrieved_memories": retrieved_mems,
        "injected_profile_slots": injected_profile_slots,
        "execution_trace": append_trace(
            state, "context_prep", started_at,
            input_summary={"user_input": user_input[:60], "kb_id": kb_id},
            output_summary={
                "context_messages_count": len(context_messages),
                "memory_facts_injected": len(retrieved_mems),
                "profile_slots_injected": len(injected_profile_slots),
                "summary_len": len(summary),
            },
        ),
    }

