"""
对话业务逻辑层

职责：
1. ChatSession CRUD（创建/列表/删除会话）
2. ChatMessage 持久化（保存用户消息 + Agent 回复）
3. 摘要压缩记忆：当历史消息累计超过阈值时，调 LLM 把旧消息压缩成 summary，再清掉旧消息
4. 调用 LangGraph 主图执行一轮对话
"""
import json
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.agent.graph import get_agent_graph
from app.agent.llm import get_llm
from app.agent.state import AgentState, make_initial_state
from app.core.prompt_guard import GUARD_REINFORCEMENT, maybe_warn
from app.models.chat import AgentSource, ChatMessage, ChatSession, MessageRole

# 压缩阈值：当一次会话中的消息条数超过此值时，触发摘要压缩
SUMMARY_TRIGGER_MESSAGES = 20
# 压缩后保留最近 N 条消息原文
KEEP_RECENT_MESSAGES = 6

_SUMMARY_PROMPT = """你是对话摘要器。请把下面这段历史对话压缩成简短的摘要（不超过 300 字），
保留关键信息：用户的主要问题、Agent 给出的结论、提到的实体（如城市、人物、文件名等）。
摘要将用于后续轮次的上下文，所以信息要紧凑准确。

之前的摘要（如有）：
{prev_summary}

需要压缩的历史对话：
{history}

请输出新的摘要，不要包含其他任何文字。"""


class ChatService:
    """对话业务方法集合"""

    # ---------- Session CRUD ----------
    @staticmethod
    def create_session(
        db: Session,
        user_id: int,
        title: str = "新对话",
        kb_id: Optional[int] = None,
    ) -> ChatSession:
        session = ChatSession(
            user_id=user_id,
            kb_id=kb_id,
            title=title,
            summary=None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def get_session(db: Session, session_id: int) -> Optional[ChatSession]:
        return db.get(ChatSession, session_id)

    @staticmethod
    def list_sessions(db: Session, user_id: int) -> List[ChatSession]:
        return (
            db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )

    @staticmethod
    def list_messages(db: Session, session_id: int) -> List[ChatMessage]:
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .all()
        )

    @staticmethod
    def delete_session(db: Session, session: ChatSession) -> None:
        # cascade='all, delete-orphan' 会自动清理 messages
        db.delete(session)
        db.commit()

    @staticmethod
    def update_session(
        db: Session,
        session: ChatSession,
        title: Optional[str] = None,
        kb_id: Optional[int] = None,
    ) -> ChatSession:
        """部分更新会话字段（标题、关联知识库）"""
        if title is not None:
            session.title = title
        if kb_id is not None:
            session.kb_id = kb_id
        db.commit()
        db.refresh(session)
        return session

    # ---------- 摘要压缩 ----------
    @staticmethod
    def _compress_if_needed(db: Session, session: ChatSession) -> None:
        """
        若会话消息超过阈值，触发摘要压缩：
        1. 取出所有除最近 N 条外的旧消息
        2. 调 LLM 生成新摘要（结合上一版摘要）
        3. 删除旧消息行，把新摘要写回 session.summary
        """
        messages = ChatService.list_messages(db, session.id)
        if len(messages) <= SUMMARY_TRIGGER_MESSAGES:
            return

        # 按时间序，前段是需要压缩的；尾部 KEEP_RECENT_MESSAGES 条保留原文
        to_compress = messages[:-KEEP_RECENT_MESSAGES]
        if not to_compress:
            return

        history_text = "\n".join(
            f"[{m.role.value}] {m.content[:300]}" for m in to_compress
        )
        prompt = _SUMMARY_PROMPT.format(
            prev_summary=session.summary or "(无)",
            history=history_text,
        )
        try:
            llm = get_llm()
            new_summary = llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=500,
            )
        except Exception as e:
            logger.warning("摘要压缩失败，跳过本次压缩: {}", e)
            return

        session.summary = new_summary.strip()
        # 删除已压缩的旧消息
        for m in to_compress:
            db.delete(m)
        db.commit()
        logger.info(
            "[Memory] 会话 {} 摘要压缩：清理 {} 条旧消息，新摘要长度 {}",
            session.id, len(to_compress), len(new_summary),
        )

    # ---------- 主流程：执行一轮对话 ----------
    @staticmethod
    def chat_once(
        db: Session,
        session: ChatSession,
        user_input: str,
    ) -> Tuple[ChatMessage, AgentState]:
        """
        执行一轮非流式对话：
        1. 保存用户消息
        2. 触发摘要压缩（如需）
        3. 构造 AgentState，调 LangGraph
        4. 保存 Agent 回复
        5. 返回 assistant message + 完整 state（含 execution_trace）
        """
        # 1. 保存用户消息
        user_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.USER,
            content=user_input,
            agent_source=AgentSource.USER,
        )
        db.add(user_msg)
        db.commit()

        # 2. 摘要压缩（在调 Agent 之前做，避免 summary 过期）
        ChatService._compress_if_needed(db, session)
        db.refresh(session)

        # 3. 构造 AgentState 并执行
        # 拼接上下文：summary + 最近对话记录（确保 Router 能感知多轮对话语境）
        effective_summary = session.summary or ""
        recent_msgs = ChatService.list_messages(db, session.id)
        # 排除刚保存的当前用户消息（最后一条），取之前的最近几条
        history_msgs = recent_msgs[:-1] if recent_msgs else []
        if history_msgs:
            recent_text = "\n".join(
                f"[{m.role.value}] {m.content[:200]}" for m in history_msgs[-6:]
            )
            if effective_summary:
                effective_summary += f"\n\n最近对话记录：\n{recent_text}"
            else:
                effective_summary = f"最近对话记录：\n{recent_text}"
        # Prompt Injection 轻量防护：可疑输入时在 summary 后追加加固指令（不持久化）
        if maybe_warn(user_input, session.user_id):
            effective_summary += GUARD_REINFORCEMENT
        initial_state = make_initial_state(
            user_input=user_input,
            session_id=session.id,
            user_id=session.user_id,
            kb_id=session.kb_id,
            summary=effective_summary,
        )
        graph = get_agent_graph()
        final_state = graph.invoke(initial_state)

        # 4. 保存 Agent 回复
        answer = final_state.get("final_answer", "") or "（无输出）"
        # 决定 agent_source
        intent = final_state.get("intent", "")
        if intent == "rag":
            src = AgentSource.RAG
        elif intent == "tool":
            src = AgentSource.TOOL
        elif intent == "router":
            src = AgentSource.ROUTER
        else:
            src = AgentSource.TOOL if final_state.get("skill_used") else AgentSource.ROUTER

        # tool_calls_json 安全序列化（含可能的不可序列化对象时降级）
        tool_calls_payload = None
        try:
            tool_calls_payload = json.loads(
                json.dumps(final_state.get("tool_calls", []), default=str)
            )
        except Exception:
            tool_calls_payload = [{"error": "serialization_failed"}]

        assistant_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            agent_source=src,
            tool_calls_json=tool_calls_payload,
            token_usage=final_state.get("total_tokens", 0) or None,
        )
        db.add(assistant_msg)

        # 如果是会话第 1 条用户消息，把它作为会话标题
        if session.title == "新对话":
            session.title = user_input[:30] + ("…" if len(user_input) > 30 else "")

        db.commit()
        db.refresh(assistant_msg)

        return assistant_msg, final_state

    # ---------- 流式版本（SSE）----------
    @staticmethod
    async def chat_stream(
        db: Session,
        session: ChatSession,
        user_input: str,
    ):
        """
        异步生成器，yield (event_type, data) 元组。

        事件序列：
        1. status   - {step: "user_saved"}             用户消息已保存
        2. status   - {step: "thinking"}                Agent 开始思考
        3. meta     - {intent, route_reason, skill_used} Router 决策结果（图执行完才有）
        4. chunk    - {text: "..."}                     回答的一段字符（多次）
        5. done     - {message_id, tool_calls, execution_trace, retrieved_docs, token_usage}

        注意：当前是"准流式"——图执行同步完成后再按字符 yield。
        要真正的 LLM token-by-token 流式需要重构 LLM 客户端（待后续优化）。
        """
        import asyncio
        from app.agent.graph import get_agent_graph
        from app.agent.state import make_initial_state

        # ---------- 1. 保存用户消息 ----------
        user_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.USER,
            content=user_input,
            agent_source=AgentSource.USER,
        )
        db.add(user_msg)
        db.commit()
        yield ("status", {"step": "user_saved", "user_msg_id": user_msg.id})

        # ---------- 2. 摘要压缩 ----------
        ChatService._compress_if_needed(db, session)
        db.refresh(session)
        yield ("status", {"step": "thinking"})

        # ---------- 3. 跑 LangGraph（同步阻塞，未来可改成 astream）----------
        # 拼接上下文：summary + 最近对话记录（同 chat_once）
        effective_summary = session.summary or ""
        recent_msgs = ChatService.list_messages(db, session.id)
        # 排除刚保存的当前用户消息（最后一条），取之前的最近几条
        history_msgs = recent_msgs[:-1] if recent_msgs else []
        if history_msgs:
            recent_text = "\n".join(
                f"[{m.role.value}] {m.content[:200]}" for m in history_msgs[-6:]
            )
            if effective_summary:
                effective_summary += f"\n\n最近对话记录：\n{recent_text}"
            else:
                effective_summary = f"最近对话记录：\n{recent_text}"
        # Prompt Injection 轻量防护（同 chat_once）
        if maybe_warn(user_input, session.user_id):
            effective_summary += GUARD_REINFORCEMENT
        initial_state = make_initial_state(
            user_input=user_input,
            session_id=session.id,
            user_id=session.user_id,
            kb_id=session.kb_id,
            summary=effective_summary,
        )
        graph = get_agent_graph()
        # 让 LangGraph 跑在线程池里，避免 block 异步事件循环
        final_state = await asyncio.to_thread(graph.invoke, initial_state)

        intent = final_state.get("intent", "")
        # 先发 meta，前端可以立刻展示 Router 决策
        yield (
            "meta",
            {
                "intent": intent,
                "route_reason": final_state.get("route_reason", ""),
                "skill_used": final_state.get("skill_used"),
            },
        )

        # ---------- 4. 按字符流式发送回答 ----------
        answer = final_state.get("final_answer", "") or "（无输出）"
        chunk_size = 4  # 每 4 字符一组（平衡感知速度和事件数量）
        for i in range(0, len(answer), chunk_size):
            yield ("chunk", {"text": answer[i : i + chunk_size]})
            # 极轻的延迟让"打字机"效果可感知（中文：每字 ~5ms）
            await asyncio.sleep(0.015)

        # ---------- 5. 保存 assistant 消息 ----------
        if intent == "rag":
            src = AgentSource.RAG
        elif intent == "tool":
            src = AgentSource.TOOL
        elif intent == "router":
            src = AgentSource.ROUTER
        else:
            src = AgentSource.TOOL if final_state.get("skill_used") else AgentSource.ROUTER

        tool_calls_payload = None
        try:
            tool_calls_payload = json.loads(
                json.dumps(final_state.get("tool_calls", []), default=str)
            )
        except Exception:
            tool_calls_payload = [{"error": "serialization_failed"}]

        assistant_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            agent_source=src,
            tool_calls_json=tool_calls_payload,
            token_usage=final_state.get("total_tokens", 0) or None,
        )
        db.add(assistant_msg)

        if session.title == "新对话":
            session.title = user_input[:30] + ("…" if len(user_input) > 30 else "")

        db.commit()
        db.refresh(assistant_msg)

        # ---------- 6. 发送 done + 完整元数据 ----------
        # tool_calls / execution_trace 已确保是可 JSON 序列化的
        execution_trace = json.loads(
            json.dumps(final_state.get("execution_trace", []), default=str)
        )
        retrieved_docs = json.loads(
            json.dumps(final_state.get("retrieved_docs", []), default=str)
        )
        yield (
            "done",
            {
                "message_id": assistant_msg.id,
                "session_id": session.id,
                "tool_calls": tool_calls_payload or [],
                "execution_trace": execution_trace,
                "retrieved_docs": retrieved_docs,
                "token_usage": final_state.get("total_tokens", 0) or 0,
                "agent_source": src.value if hasattr(src, "value") else str(src),
            },
        )
