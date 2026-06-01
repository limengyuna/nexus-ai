"""
L2 记忆事实抽取后台异步任务

通过多线程异步运行抽取任务，避免阻塞主对话的 SSE 响应。
特别注意：由于 ORM 对象无法跨线程安全使用，异步任务通过传递消息 ID 并在新线程的数据库会话中重新查询。
"""
import threading
from typing import Any, Dict, List
from loguru import logger

from app.core.database import SessionLocal
from app.models.chat import ChatMessage
from app.memory.extractor import MemoryExtractor
from app.memory.store import MemoryStore
from app.memory.profile_extractor import ProfileExtractor
from app.memory.profile_store import MemoryProfileStore


def _extract_error_facts_worker(
    user_id: int,
    session_id: int,
    user_input: str,
    error_calls: List[Dict[str, Any]],
    kb_id: int | None = None
) -> None:
    """工具调用错误事实抽取的子线程执行逻辑"""
    logger.info("[Memory Tasks] 开始后台提取工具错误教训... (user_id={}, session_id={})", user_id, session_id)
    db = SessionLocal()
    try:
        # 1. 调用大模型提取教训
        extracted_facts = MemoryExtractor.extract_from_error_calls(user_input, error_calls)
        
        # 2. 将结果存入 L2 数据库和向量库
        saved_count = 0
        for fact_dict in extracted_facts:
            try:
                # error_lesson 绑定到当前知识库
                MemoryStore.save_fact(
                    db=db,
                    user_id=user_id,
                    content=fact_dict["content"],
                    fact_type=fact_dict["fact_type"],
                    importance=fact_dict["importance"],
                    session_id=session_id,
                    kb_id=kb_id
                )
                saved_count += 1
            except Exception as e:
                logger.error("[Memory Tasks] 保存错误教训失败: {}", e)
        
        logger.info("[Memory Tasks] 后台错误教训提取执行完毕，成功保存 {}/{} 条事实", saved_count, len(extracted_facts))
    except Exception as e:
        logger.exception("[Memory Tasks] 运行后台错误教训提取任务失败: {}", e)
    finally:
        db.close()


def _extract_batch_facts_worker(
    user_id: int,
    session_id: int,
    message_ids: List[int],
    kb_id: int | None = None
) -> None:
    """历史对话批量事实抽取的子线程执行逻辑"""
    logger.info("[Memory Tasks] 开始后台批量提取历史事实... (user_id={}, session_id={}, 消息数={})", user_id, session_id, len(message_ids))
    db = SessionLocal()
    try:
        # 1. 重新从数据库查询消息，确保跨线程 ORM 的安全性
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.id.in_(message_ids))
            .order_by(ChatMessage.id)
            .all()
        )
        if not messages:
            logger.warning("[Memory Tasks] 未找到对应的归档历史消息，退出任务")
            return

        # 2. 调用大模型提取长期事实
        extracted_facts = MemoryExtractor.extract_from_history(messages)

        # 3. 将结果存入 L2 数据库和向量库
        saved_count = 0
        for fact_dict in extracted_facts:
            try:
                # 所有记忆统一为全局可见（kb_id=None），召回时靠语义相似度自然过滤
                MemoryStore.save_fact(
                    db=db,
                    user_id=user_id,
                    content=fact_dict["content"],
                    fact_type=fact_dict["fact_type"],
                    importance=fact_dict["importance"],
                    session_id=session_id,
                    kb_id=None
                )
                saved_count += 1
            except Exception as e:
                logger.error("[Memory Tasks] 保存批量事实失败: {}", e)

        logger.info("[Memory Tasks] 后台批量事实提取执行完毕，成功保存 {}/{} 条事实", saved_count, len(extracted_facts))
    except Exception as e:
        logger.exception("[Memory Tasks] 运行后台批量事实提取任务失败: {}", e)
    finally:
        db.close()


def start_async_extract_error_facts(
    user_id: int,
    session_id: int,
    user_input: str,
    error_calls: List[Dict[str, Any]],
    kb_id: int | None = None
) -> None:
    """
    触发异步任务：从工具调用错误中立即提取教训（下一轮可用）

    :param user_id: 用户 ID
    :param session_id: 来源会话 ID
    :param user_input: 当前用户的输入
    :param error_calls: 错误工具调用详情
    """
    if not error_calls:
        return

    # 创建并启动守护线程（避免阻塞 FastAPI 主响应）
    thread = threading.Thread(
        target=_extract_error_facts_worker,
        args=(user_id, session_id, user_input, error_calls, kb_id),
        daemon=True
    )
    thread.start()


def start_async_extract_batch_facts(
    user_id: int,
    session_id: int,
    messages: List[ChatMessage],
    kb_id: int | None = None
) -> None:
    """
    触发异步任务：从即将归档的历史对话中批量抽取事实

    :param user_id: 用户 ID
    :param session_id: 来源会话 ID
    :param messages: 即将进行压缩的消息列表（ChatMessage 实例列表）
    """
    if not messages:
        return

    # 提取消息 ID 列表传递，确保多线程下 ORM 安全性
    message_ids = [m.id for m in messages]

    thread = threading.Thread(
        target=_extract_batch_facts_worker,
        args=(user_id, session_id, message_ids, kb_id),
        daemon=True
    )
    thread.start()


def _extract_turn_facts_worker(
    user_id: int,
    session_id: int,
    user_input: str,
    assistant_answer: str,
    kb_id: int | None = None
) -> None:
    """每轮对话即时事实抽取的子线程执行逻辑"""
    logger.info("[Memory Tasks] 开始即时抽取当前轮事实... (user_id={}, session_id={})", user_id, session_id)
    db = SessionLocal()
    try:
        extracted_facts = MemoryExtractor.extract_from_turn(user_input, assistant_answer)
        if not extracted_facts:
            logger.debug("[Memory Tasks] 当前轮无可抽取的高价值事实")
            return

        saved_count = 0
        for fact_dict in extracted_facts:
            try:
                # 所有记忆统一为全局可见（kb_id=None），召回时靠语义相似度自然过滤
                MemoryStore.save_fact(
                    db=db,
                    user_id=user_id,
                    content=fact_dict["content"],
                    fact_type=fact_dict["fact_type"],
                    importance=fact_dict["importance"],
                    session_id=session_id,
                    kb_id=None
                )
                saved_count += 1
            except Exception as e:
                logger.error("[Memory Tasks] 保存即时事实失败: {}", e)

        logger.info("[Memory Tasks] 即时事实抽取完毕，保存 {}/{} 条", saved_count, len(extracted_facts))
    except Exception as e:
        logger.exception("[Memory Tasks] 即时事实抽取任务失败: {}", e)
    finally:
        db.close()


def start_async_extract_turn_facts(
    user_id: int,
    session_id: int,
    user_input: str,
    assistant_answer: str,
    kb_id: int | None = None
) -> None:
    """
    触发异步任务：从当前轮对话中即时抽取高价值事实

    每轮对话结束后调用，确保用户身份、明确指令、纠正反馈等
    关键信息能立即持久化到 L2，无需等待摘要压缩触发。
    依赖 MemoryStore.save_fact 的语义去重机制避免重复。

    :param user_id: 用户 ID
    :param session_id: 来源会话 ID
    :param user_input: 用户本轮输入
    :param assistant_answer: AI 本轮回复
    :param kb_id: 关联知识库 ID
    """
    if not user_input:
        return

    thread = threading.Thread(
        target=_extract_turn_facts_worker,
        args=(user_id, session_id, user_input, assistant_answer, kb_id),
        daemon=True
    )
    thread.start()


def _extract_profile_slots_worker(
    user_id: int,
    session_id: int,
    user_input: str,
    assistant_answer: str,
    source_message_id: int | None = None,
    kb_id: int | None = None
) -> None:
    """自动提取结构化偏好与候选记忆的后台子线程"""
    logger.info("[Memory Tasks] 开始后台自动提取结构化偏好... (user_id={}, session_id={})", user_id, session_id)
    db = SessionLocal()
    try:
        # 1. 查询当前所有激活的槽位
        active_slots = MemoryProfileStore.list_active_slots(db)
        if not active_slots:
            logger.warning("[Memory Tasks] 系统中没有激活的 Memory Slots，跳过提取")
            return

        # 转换为字典列表以保障线程安全
        slots_definitions = []
        for s in active_slots:
            slots_definitions.append({
                "slot_key": s.slot_key,
                "value_type": s.value_type,
                "description": s.description,
                "allowed_values": s.allowed_values
            })

        # 2. 查询当前用户已生效的档案
        user_vals = MemoryProfileStore.get_user_profile(db, user_id)
        current_profile = {}
        for val in user_vals:
            slot = next((s for s in active_slots if s.id == val.slot_id), None)
            if slot:
                current_profile[slot.slot_key] = val.slot_value

        # 3. 调用 LLM 抽取器
        result = ProfileExtractor.extract(user_input, assistant_answer, slots_definitions, current_profile)
        updates = result.get("updates", [])
        candidates = result.get("candidates", [])

        # 4. 处理更新 (updates)
        saved_updates = 0
        for upd in updates:
            slot_key = upd.get("slot_key")
            slot_value = upd.get("slot_value")
            confidence = upd.get("confidence", 0.8)
            source = upd.get("source", "inferred")
            reason = upd.get("reason", "")

            # 阈值过滤
            is_valid = False
            if source == "explicit" and confidence >= 0.75:
                is_valid = True
            elif source == "inferred" and confidence >= 0.85:
                is_valid = True

            if is_valid:
                res = MemoryProfileStore.upsert_slot_value(
                    db=db,
                    user_id=user_id,
                    slot_key=slot_key,
                    slot_value=slot_value,
                    confidence=confidence,
                    source=source,
                    source_session_id=session_id,
                    source_message_id=source_message_id,
                    updated_by="assistant"
                )
                if res:
                    saved_updates += 1
            else:
                # 达不到置信度阈值，作为候选写入
                MemoryProfileStore.create_candidate(
                    db=db,
                    user_id=user_id,
                    candidate_text=f"用户表达的槽位 {slot_key} 为: {slot_value}。原因: {reason}",
                    suggested_slot_key=slot_key,
                    suggested_value=slot_value,
                    reason=f"自动提取的偏好置信度不足（源: {source}, 置信度: {confidence}）: {reason}",
                    confidence=confidence,
                    source_session_id=session_id,
                    source_message_id=source_message_id
                )

        # 5. 处理候选偏好 (candidates)
        saved_candidates = 0
        for cand in candidates:
            candidate_text = cand.get("candidate_text")
            suggested_slot_key = cand.get("suggested_slot_key")
            suggested_value = cand.get("suggested_value")
            confidence = cand.get("confidence", 0.5)
            reason = cand.get("reason", "")

            # 过滤超低置信度数据以防垃圾数据
            if confidence >= 0.6:
                MemoryProfileStore.create_candidate(
                    db=db,
                    user_id=user_id,
                    candidate_text=candidate_text,
                    suggested_slot_key=suggested_slot_key,
                    suggested_value=suggested_value,
                    reason=reason,
                    confidence=confidence,
                    source_session_id=session_id,
                    source_message_id=source_message_id
                )
                saved_candidates += 1

        logger.info(
            "[Memory Tasks] 自动偏好提取处理完毕。成功写入槽位 {}/{} 条，候选写入 {} 条",
            saved_updates, len(updates), saved_candidates
        )
    except Exception as e:
        logger.exception("[Memory Tasks] 运行后台偏好自动提取任务失败: {}", e)
    finally:
        db.close()


def start_async_extract_profile_slots(
    user_id: int,
    session_id: int,
    user_input: str,
    assistant_answer: str,
    source_message_id: int | None = None,
    kb_id: int | None = None
) -> None:
    """
    触发异步任务：从当前轮对话中提取并更新用户偏好槽位或写入候选区。
    """
    if not user_input or not assistant_answer:
        return

    thread = threading.Thread(
        target=_extract_profile_slots_worker,
        args=(user_id, session_id, user_input, assistant_answer, source_message_id, kb_id),
        daemon=True
    )
    thread.start()
