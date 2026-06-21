"""
全局流式队列注册表

将 _token_queue 从 AgentState 中移出，改用全局注册表管理。
这样 AgentState 可以被 Checkpointer 正常序列化（queue.Queue 无法序列化）。

使用 session_id 作为键，节点通过 state["session_id"] 查找对应的队列。
"""
import functools
import queue
from typing import Dict, Optional, Any

from loguru import logger

class InterceptingQueue:
    """拦截底层队列，专门用于侦测是否向前端推送了正式 chunk"""
    def __init__(self, wrapped_queue: queue.Queue):
        self._q = wrapped_queue
        self.has_pushed_chunk = False
        
    def put(self, item, block=True, timeout=None):
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "chunk":
            # 只要有任何实质性的 chunk 推送，就立刻置位
            if item[1]:  # not empty string
                self.has_pushed_chunk = True
        self._q.put(item, block=block, timeout=timeout)
        
    def get(self, block=True, timeout=None):
        return self._q.get(block=block, timeout=timeout)
        
    def get_nowait(self):
        return self._q.get_nowait()
        
    def put_nowait(self, item):
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "chunk":
            if item[1]:
                self.has_pushed_chunk = True
        return self._q.put_nowait(item)
        
    def empty(self):
        return self._q.empty()
        
    def qsize(self):
        return self._q.qsize()
        
    def join(self):
        return self._q.join()
        
    def task_done(self):
        return self._q.task_done()


# 全局注册表：session_id → InterceptingQueue
_queues: Dict[int, InterceptingQueue] = {}


def register_queue(session_id: int, q: queue.Queue) -> None:
    """注册流式队列（chat_stream 调用前注册）"""
    _queues[session_id] = InterceptingQueue(q)
    logger.debug("[StreamQueue] 注册 session_id={}", session_id)


def get_queue(session_id: Optional[int]) -> Optional[InterceptingQueue]:
    """获取流式队列（节点内调用），非流式模式下返回 None"""
    if session_id is None:
        return None
    return _queues.get(session_id)


def unregister_queue(session_id: int) -> None:
    """注销流式队列（chat_stream 结束后清理）"""
    _queues.pop(session_id, None)
    logger.debug("[StreamQueue] 注销 session_id={}", session_id)


def with_stream_interceptor(func):
    """
    节点装饰器：自动将队列底层的 chunk 拦截状态写回到 LangGraph state 中。
    让各个子 Agent 开发者免于手动判断和写入 public_answer_started。
    """
    @functools.wraps(func)
    def wrapper(state: dict) -> dict:
        result = func(state)
        
        # 如果节点已经显式返回了，尊重节点的返回
        if "public_answer_started" in result:
            return result
            
        session_id = state.get("session_id")
        q = get_queue(session_id)
        
        # 只要底层拦截到过 chunk 推送，就在本次节点结束时统一更新 state
        if q and q.has_pushed_chunk:
            result["public_answer_started"] = True
            
        return result
    return wrapper
