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
# 参考 LangChain ConversationSummaryBufferMemory，5 轮对话（10 条消息）触发
SUMMARY_TRIGGER_MESSAGES = 10
# 压缩后保留最近 N 条消息原文（2 轮完整交互）
KEEP_RECENT_MESSAGES = 4

_SUMMARY_PROMPT = """你是对话摘要器。请把下面这段历史对话压缩成简短的摘要（不超过 500 字），
保留关键信息：用户的主要问题、Agent 给出的结论、提到的实体（如城市、人物、文件名等）。
摘要将用于后续轮次的上下文，所以信息要紧凑准确。

之前的摘要（如有）：
{prev_summary}

需要压缩的历史对话：
{history}

请输出新的摘要，不要包含其他任何文字。"""


def _format_msg_for_context(m: ChatMessage) -> str:
    """
    格式化单条消息用于跨轮上下文拼接。
    对 assistant 消息，附加工具调用摘要（成功/失败），
    确保后续轮次 LLM 能感知之前的工具调用过程。
    """
    base = f"[{m.role.value}] {m.content[:200]}"
    if m.role.value == "assistant" and m.tool_calls_json:
        calls = m.tool_calls_json if isinstance(m.tool_calls_json, list) else []
        if not calls:
            return base
        error_calls = [c for c in calls if c.get("error")]
        success_names = [c.get("name", "?") for c in calls if not c.get("error")]
        parts = []
        if success_names:
            parts.append(f"成功调用: {', '.join(success_names[:5])}")
        for c in error_calls[:3]:
            err_msg = str(c.get("error", ""))[:80]
            parts.append(f"调用 {c.get('name','?')} 失败: {err_msg}")
        if parts:
            base += f"\n  [工具记录] {'; '.join(parts)}"
    return base


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
        """返回会话所有消息（含已归档），供前端展示完整历史"""
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .all()
        )

    @staticmethod
    def list_active_messages(db: Session, session_id: int) -> List[ChatMessage]:
        """返回会话中未归档的消息（供摘要压缩判断和 Agent 上下文构建使用）"""
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.is_archived == False)  # noqa: E712
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
        若会话活跃消息超过阈值，触发摘要压缩：
        1. 取出所有除最近 N 条外的旧消息
        2. 调 LLM 生成新摘要（结合上一版摘要）
        3. 标记旧消息为已归档（is_archived=True），把新摘要写回 session.summary
        """
        messages = ChatService.list_active_messages(db, session.id)
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
                max_tokens=800,
            )
        except Exception as e:
            logger.warning("摘要压缩失败，跳过本次压缩: {}", e)
            return

        session.summary = new_summary.strip()
        # 软删除：标记为已归档，保留完整历史供前端浏览
        for m in to_compress:
            m.is_archived = True
        db.commit()

        # 触发 L2 记忆：异步批量提取这批归档消息中的长效事实与用户偏好
        try:
            from app.memory.tasks import start_async_extract_batch_facts
            start_async_extract_batch_facts(
                user_id=session.user_id,
                session_id=session.id,
                messages=to_compress,
                kb_id=session.kb_id
            )
        except Exception as e:
            logger.error("[Memory Integration] 异步触发批量事实提取失败: {}", e)

        logger.info(
            "[Memory] 会话 {} 摘要压缩：归档 {} 条旧消息，新摘要长度 {}",
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
                _format_msg_for_context(m) for m in history_msgs[-8:]
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
        # 每条用户消息独立 thread（方案 A）：thread_id = turn-{user_msg.id}
        # 支持后续通过 resume 端点恢复（chat_once 路径下若中断，调用方需自行处理）
        from app.agent.checkpoint import make_thread_config
        thread_config = make_thread_config(user_msg.id)
        final_state = graph.invoke(initial_state, config=thread_config)

        # 4. 保存 Agent 回复
        answer = final_state.get("final_answer", "") or "（无输出）"
        # 决定 agent_source（Supervisor 架构下 intent 由 Supervisor 设置）
        intent = final_state.get("intent", "")
        if intent == "rag":
            src = AgentSource.RAG
        elif intent == "tool":
            src = AgentSource.TOOL
        else:
            src = AgentSource.ROUTER

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

        # 触发 L2 记忆：检查是否有工具调用发生错误，若有则触发后台异步提取教训
        tool_calls = final_state.get("tool_calls", [])
        error_calls = [tc for tc in tool_calls if tc.get("error")]
        if error_calls:
            try:
                from app.memory.tasks import start_async_extract_error_facts
                start_async_extract_error_facts(
                    user_id=session.user_id,
                    session_id=session.id,
                    user_input=user_input,
                    error_calls=error_calls,
                    kb_id=session.kb_id
                )
            except Exception as e:
                logger.error("[Memory Integration] 异步触发工具错误事实提取失败: {}", e)

        # 触发 L2 记忆：每轮即时抽取高价值事实（用户身份、明确指令、纠正反馈等）
        try:
            from app.memory.tasks import start_async_extract_turn_facts
            start_async_extract_turn_facts(
                user_id=session.user_id,
                session_id=session.id,
                user_input=user_input,
                assistant_answer=answer,
                kb_id=session.kb_id
            )
        except Exception as e:
            logger.error("[Memory Integration] 异步触发每轮事实抽取失败: {}", e)

        return assistant_msg, final_state

    # ---------- 流式辅助：消费 token_queue → yield SSE 事件 ----------
    @staticmethod
    async def _consume_stream_queue(token_queue, graph_task):
        """
        消费节点推送的流式事件，转成 SSE 元组 yield 出去。

        终止条件（任一满足即返回）：
        - 收到 ("done", None) 事件
        - graph_task 已完成（含异常退出 / 触发 interrupt 后的提前返回）

        被 chat_stream 和 chat_resume_stream 共用。
        """
        import asyncio
        import queue as queue_mod

        stream_done = False
        while not stream_done:
            has_event = False
            while True:
                try:
                    event_type, data = token_queue.get_nowait()
                    has_event = True
                except queue_mod.Empty:
                    break
                if event_type == "meta":
                    yield ("meta", data)
                elif event_type == "chunk":
                    yield ("chunk", {"text": data})
                elif event_type == "approval_pending":
                    # tool_agent 在 interrupt() 之前推送的"即将中断"提示（可选体验）
                    yield ("approval_pending", data)
                elif event_type == "done":
                    stream_done = True
                    break

            if stream_done:
                break

            # 图异常退出 / interrupt 触发：graph_task 提前完成
            if graph_task.done():
                exc = graph_task.exception()
                if exc:
                    logger.error("[ChatService] Agent graph 异常退出: {}", exc)
                    yield ("chunk", {"text": f"\n\n[Agent 执行出错: {exc}]"})
                break

            if not has_event:
                await asyncio.sleep(0.02)

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
        3. meta     - {intent, route_reason, skill_used} Router 决策（由终端节点推送）
        4. chunk    - {text: "..."}                     真流式 token（多次）
        5. done     - {message_id, tool_calls, execution_trace, retrieved_docs, token_usage}

        实现方式：graph.invoke 在后台线程运行，终端节点（fallback/rag/tool）通过
        _token_queue 实时推送 meta/chunk/done 事件，本方法并行消费队列并 yield。
        Fallback 和 RAG 使用 LLM complete_stream 逐 token 推送（真流式）。
        Tool Agent 在工具调用完成后一次性推送最终答案。
        """
        import asyncio
        import queue as queue_mod
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

        # ---------- 3. 构造 AgentState + 注入流式队列 ----------
        effective_summary = session.summary or ""
        recent_msgs = ChatService.list_messages(db, session.id)
        history_msgs = recent_msgs[:-1] if recent_msgs else []
        if history_msgs:
            recent_text = "\n".join(
                _format_msg_for_context(m) for m in history_msgs[-8:]
            )
            if effective_summary:
                effective_summary += f"\n\n最近对话记录：\n{recent_text}"
            else:
                effective_summary = f"最近对话记录：\n{recent_text}"
        if maybe_warn(user_input, session.user_id):
            effective_summary += GUARD_REINFORCEMENT

        token_queue: queue_mod.Queue = queue_mod.Queue()
        initial_state = make_initial_state(
            user_input=user_input,
            session_id=session.id,
            user_id=session.user_id,
            kb_id=session.kb_id,
            summary=effective_summary,
        )
        # 流式队列注册到全局表（state 不再持有 Queue，避免 Checkpointer 序列化失败）
        from app.agent.stream_queue import register_queue, unregister_queue
        from app.agent.cancel_registry import clear_cancel
        from app.agent.checkpoint import make_thread_config
        register_queue(session.id, token_queue)
        # 清除上一轮可能残留的 cancel 标记（协调层是内存字典，
        # 如果上一轮被取消但未清理，本轮一启动就会被误判为已取消）
        clear_cancel(session.id)
        thread_config = make_thread_config(user_msg.id)

        graph = get_agent_graph()

        # ---------- 4. 后台线程执行 LangGraph，同时消费队列 ----------
        graph_task = asyncio.ensure_future(
            asyncio.to_thread(graph.invoke, initial_state, thread_config)
        )

        try:
            async for ev in ChatService._consume_stream_queue(token_queue, graph_task):
                yield ev
        finally:
            # 流式结束（无论正常/异常）必须注销队列，避免内存泄漏
            unregister_queue(session.id)
            # 顺便清掉 cancel 标记，避免遗留影响后续会话
            clear_cancel(session.id)

        # ---------- 5. 等待图执行完成，获取完整 state ----------
        try:
            final_state = await graph_task
        except Exception as e:
            logger.exception("[ChatService] Agent graph 执行失败: {}", e)
            final_state = initial_state  # 降级

        # ---------- 5.1 检测 interrupt：图未真正结束，等待用户审批 ----------
        # LangGraph 0.3.x：graph.invoke() 返回值不含 __interrupt__，
        # 必须通过 graph.get_state(config) 获取 StateSnapshot 来检测中断
        state_snapshot = await asyncio.to_thread(graph.get_state, thread_config)
        if state_snapshot.next:
            # state_snapshot.next 非空 → 图还有待执行节点，说明被 interrupt 了
            interrupt_value = None
            for task in (state_snapshot.tasks or []):
                if hasattr(task, 'interrupts') and task.interrupts:
                    interrupt_value = task.interrupts[0].value
                    break
            if interrupt_value is None:
                interrupt_value = {"message": "Agent 执行被中断，请审批后继续"}
            logger.info("[ChatService] 检测到 interrupt，等待用户审批: {}", interrupt_value)
            yield ("interrupt", {
                "user_msg_id": user_msg.id,           # 前端 resume 时传回，定位 thread_id
                "session_id": session.id,
                "payload": interrupt_value,           # build_approval_payload 构造的内容
            })
            # 不保存 assistant message（对话未完成），直接返回；后续靠 chat_resume_stream
            return

        # ---------- 6. 保存 assistant 消息 ----------
        answer = final_state.get("final_answer", "") or "（无输出）"
        intent = final_state.get("intent", "")

        # Supervisor 架构下 intent 由 Supervisor 设置
        if intent == "rag":
            src = AgentSource.RAG
        elif intent == "tool":
            src = AgentSource.TOOL
        else:
            src = AgentSource.ROUTER

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

        # 触发 L2 记忆：检查是否有工具调用发生错误，若有则触发后台异步提取教训
        tool_calls = final_state.get("tool_calls", [])
        error_calls = [tc for tc in tool_calls if tc.get("error")]
        if error_calls:
            try:
                from app.memory.tasks import start_async_extract_error_facts
                start_async_extract_error_facts(
                    user_id=session.user_id,
                    session_id=session.id,
                    user_input=user_input,
                    error_calls=error_calls,
                    kb_id=session.kb_id
                )
            except Exception as e:
                logger.error("[Memory Integration] 异步触发工具错误事实提取失败: {}", e)

        # 触发 L2 记忆：每轮即时抽取高价值事实（用户身份、明确指令、纠正反馈等）
        try:
            from app.memory.tasks import start_async_extract_turn_facts
            start_async_extract_turn_facts(
                user_id=session.user_id,
                session_id=session.id,
                user_input=user_input,
                assistant_answer=answer,
                kb_id=session.kb_id
            )
        except Exception as e:
            logger.error("[Memory Integration] 异步触发每轮事实抽取失败: {}", e)

        # ---------- 7. 发送 done + 完整元数据 ----------
        execution_trace = json.loads(
            json.dumps(final_state.get("execution_trace", []), default=str)
        )
        retrieved_docs = json.loads(
            json.dumps(final_state.get("retrieved_docs", []), default=str)
        )
        retrieved_memories = json.loads(
            json.dumps(final_state.get("retrieved_memories", []), default=str)
        )
        task_plan = json.loads(
            json.dumps(final_state.get("task_plan", []), default=str)
        )
        faithfulness = json.loads(
            json.dumps(final_state.get("faithfulness", {}), default=str)
        )
        yield (
            "done",
            {
                "message_id": assistant_msg.id,
                "session_id": session.id,
                "tool_calls": tool_calls_payload or [],
                "execution_trace": execution_trace,
                "retrieved_docs": retrieved_docs,
                "retrieved_memories": retrieved_memories,
                "task_plan": task_plan,
                "faithfulness": faithfulness,
                "token_usage": final_state.get("total_tokens", 0) or 0,
                "agent_source": src.value if hasattr(src, "value") else str(src),
            },
        )

    # ---------- 流式版本（SSE）—— 中断恢复 ----------
    @staticmethod
    async def chat_resume_stream(
        db: Session,
        session: ChatSession,
        user_msg_id: int,
        decision: dict,
    ):
        """
        恢复一个被 interrupt() 暂停的对话轮次。

        :param session: 会话对象
        :param user_msg_id: 原始用户消息 ID（用于定位 thread_id）
        :param decision: 用户审批决定，形如：
            {"action": "approve"|"reject", "reason": "...", "edited_args": {...}}

        事件序列与 chat_stream 相同：可能再次产生 interrupt 事件（多次审批场景）。
        """
        import asyncio
        import queue as queue_mod
        from app.agent.graph import get_agent_graph
        from app.agent.stream_queue import register_queue, unregister_queue
        from app.agent.checkpoint import make_thread_config
        from langgraph.types import Command

        # 校验原 user_msg 存在且属于本 session
        user_msg = db.get(ChatMessage, user_msg_id)
        if user_msg is None or user_msg.session_id != session.id:
            yield ("chunk", {"text": f"\n\n[恢复失败：未找到 user_msg_id={user_msg_id}]"})
            return
        user_input = user_msg.content

        # ---------- Cursor 风格智能续跑：识别 decision.user_message ----------
        # 当用户在中断后发送新消息时，前端会把消息作为 decision.user_message 传过来。
        # 这里要做两件事：
        # 1) 写一条新的 user_message 到 db（保持对话历史完整）
        # 2) 把它附加到 user_input 上下文，并保留在 decision 中给 supervisor 节点使用
        # supervisor 节点会从 Command(resume=decision) 的返回值里读到 user_message，
        # 注入 LLM 上下文，由 LLM 自己判断：续跑剩余 step 还是放弃旧 plan 重新规划。
        new_user_message_text = (decision or {}).get("user_message")
        if new_user_message_text:
            logger.info(
                "[ChatService.resume] 检测到用户中断后的新消息，写入 db 并注入 decision: '{}...'",
                new_user_message_text[:50]
            )
            new_user_msg = ChatMessage(
                session_id=session.id,
                role=MessageRole.USER,
                content=new_user_message_text,
            )
            db.add(new_user_msg)
            db.commit()
            db.refresh(new_user_msg)
            # 把 user_input 也更新为最新消息（用于后续会话标题、错误日志等）
            user_input = new_user_message_text

        yield ("status", {"step": "resuming", "user_msg_id": user_msg_id})

        # 准备流式队列与 thread 配置
        from app.agent.cancel_registry import clear_cancel
        token_queue: queue_mod.Queue = queue_mod.Queue()
        register_queue(session.id, token_queue)
        clear_cancel(session.id)  # 清除上一轮残留 cancel 标记
        thread_config = make_thread_config(user_msg_id)

        graph = get_agent_graph()

        logger.info(
            "[ChatService.resume] start: session={}, user_msg_id={}, decision={}",
            session.id, user_msg_id, decision,
        )

        # 关键：用 Command(resume=...) 恢复，而不是传新 state
        # LangGraph 会从 checkpointer 加载该 thread 的最后一个 checkpoint，
        # 在 interrupt() 点继续执行，并把 decision 作为 interrupt 的返回值
        graph_task = asyncio.ensure_future(
            asyncio.to_thread(graph.invoke, Command(resume=decision), thread_config)
        )

        event_count = 0
        try:
            async for ev in ChatService._consume_stream_queue(token_queue, graph_task):
                event_count += 1
                logger.debug("[ChatService.resume] yield event #{}: type={}", event_count, ev[0])
                yield ev
        finally:
            unregister_queue(session.id)
            clear_cancel(session.id)
            logger.info("[ChatService.resume] consume queue end, total events yielded: {}", event_count)

        # 等待图执行完成
        try:
            final_state = await graph_task
        except Exception as e:
            logger.exception("[ChatService] resume graph 执行失败: {}", e)
            yield ("chunk", {"text": f"\n\n[恢复执行出错: {e}]"})
            return

        # 二次中断检测（多次审批场景）
        # 同样通过 graph.get_state() 检测，而非检查返回值中的 __interrupt__
        state_snapshot = await asyncio.to_thread(graph.get_state, thread_config)
        if state_snapshot.next:
            interrupt_value = None
            for task in (state_snapshot.tasks or []):
                if hasattr(task, 'interrupts') and task.interrupts:
                    interrupt_value = task.interrupts[0].value
                    break
            if interrupt_value is None:
                interrupt_value = {"message": "Agent 执行被中断，请审批后继续"}
            logger.info("[ChatService] resume 后再次 interrupt: {}", interrupt_value)
            yield ("interrupt", {
                "user_msg_id": user_msg_id,
                "session_id": session.id,
                "payload": interrupt_value,
            })
            return

        # ---------- 保存 assistant 消息（与 chat_stream 后半段一致）----------
        answer = final_state.get("final_answer", "") or "（无输出）"
        intent = final_state.get("intent", "")
        if intent == "rag":
            src = AgentSource.RAG
        elif intent == "tool":
            src = AgentSource.TOOL
        else:
            src = AgentSource.ROUTER

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

        # L2 记忆触发（与 chat_stream 一致）
        tool_calls = final_state.get("tool_calls", [])
        error_calls = [tc for tc in tool_calls if tc.get("error")]
        if error_calls:
            try:
                from app.memory.tasks import start_async_extract_error_facts
                start_async_extract_error_facts(
                    user_id=session.user_id, session_id=session.id,
                    user_input=user_input, error_calls=error_calls, kb_id=session.kb_id,
                )
            except Exception as e:
                logger.error("[Memory Integration] resume 异步触发工具错误事实失败: {}", e)
        try:
            from app.memory.tasks import start_async_extract_turn_facts
            start_async_extract_turn_facts(
                user_id=session.user_id, session_id=session.id,
                user_input=user_input, assistant_answer=answer, kb_id=session.kb_id,
            )
        except Exception as e:
            logger.error("[Memory Integration] resume 异步触发每轮事实失败: {}", e)

        # 发送 done
        yield (
            "done",
            {
                "message_id": assistant_msg.id,
                "session_id": session.id,
                "tool_calls": tool_calls_payload or [],
                "execution_trace": json.loads(
                    json.dumps(final_state.get("execution_trace", []), default=str)
                ),
                "retrieved_docs": json.loads(
                    json.dumps(final_state.get("retrieved_docs", []), default=str)
                ),
                "retrieved_memories": json.loads(
                    json.dumps(final_state.get("retrieved_memories", []), default=str)
                ),
                "task_plan": json.loads(
                    json.dumps(final_state.get("task_plan", []), default=str)
                ),
                "faithfulness": json.loads(
                    json.dumps(final_state.get("faithfulness", {}), default=str)
                ),
                "token_usage": final_state.get("total_tokens", 0) or 0,
                "agent_source": src.value if hasattr(src, "value") else str(src),
                "resumed": True,
            },
        )
