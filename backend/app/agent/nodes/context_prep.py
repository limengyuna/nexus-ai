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

    # 注入 L2 语义事实库的相关历史事实与教训记忆
    retrieved_mems = []
    if user_id:
        from app.core.database import SessionLocal
        from app.memory.retriever import MemoryRetriever
        
        db = SessionLocal()
        try:
            relevant_facts = MemoryRetriever.retrieve(db, user_input, user_id, kb_id=kb_id, top_k=3)
            if relevant_facts:
                facts_text = "\n".join(f"- {f.content}" for f in relevant_facts)
                context_messages.append({
                    "role": "system",
                    "content": f"以下是从你（Agent）的历史执行经验/教训/用户偏好中检索到的最相关的记忆，请作为强力参考规则（尤其是避免再次出现类似的错误）：\n{facts_text}",
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
            logger.exception("[Context Prep] 从 L2 记忆事实库检索并注入时发生异常: {}", e)
        finally:
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
        "execution_trace": append_trace(
            state, "context_prep", started_at,
            input_summary={"user_input": user_input[:60], "kb_id": kb_id},
            output_summary={
                "context_messages_count": len(context_messages),
                "memory_facts_injected": len(retrieved_mems),
                "summary_len": len(summary),
            },
        ),
    }

