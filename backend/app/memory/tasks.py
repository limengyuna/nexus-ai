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
                # preference 类型为全局记忆，不绑定 kb_id
                fact_kb_id = None if fact_dict["fact_type"] == "preference" else kb_id
                MemoryStore.save_fact(
                    db=db,
                    user_id=user_id,
                    content=fact_dict["content"],
                    fact_type=fact_dict["fact_type"],
                    importance=fact_dict["importance"],
                    session_id=session_id,
                    kb_id=fact_kb_id
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
