"""
全局流式队列注册表

将 _token_queue 从 AgentState 中移出，改用全局注册表管理。
这样 AgentState 可以被 Checkpointer 正常序列化（queue.Queue 无法序列化）。

使用 session_id 作为键，节点通过 state["session_id"] 查找对应的队列。
"""
import queue
from typing import Dict, Optional

from loguru import logger

# 全局注册表：session_id → Queue
_queues: Dict[int, queue.Queue] = {}


def register_queue(session_id: int, q: queue.Queue) -> None:
    """注册流式队列（chat_stream 调用前注册）"""
    _queues[session_id] = q
    logger.debug("[StreamQueue] 注册 session_id={}", session_id)


def get_queue(session_id: Optional[int]) -> Optional[queue.Queue]:
    """获取流式队列（节点内调用），非流式模式下返回 None"""
    if session_id is None:
        return None
    return _queues.get(session_id)


def unregister_queue(session_id: int) -> None:
    """注销流式队列（chat_stream 结束后清理）"""
    _queues.pop(session_id, None)
    logger.debug("[StreamQueue] 注销 session_id={}", session_id)
