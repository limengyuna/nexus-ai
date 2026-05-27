"""
取消信号注册表（协调层）

职责：
- 让 HTTP 请求处理线程（写者）和 graph 执行线程（读者）跨线程通讯
- 仅承载"是否被取消"这一信号，不承载业务数据
- 重启即丢失（与 stream_queue 同构，纯内存协调机制）

使用约定：
- 写：API 层接收到 /cancel 请求时调用 request_cancel(session_id)
- 读：节点（supervisor / tool_agent / rag_agent）在长循环或入口处轮询 is_cancelled
- 清：每次新一轮 chat_stream 启动时调用 clear_cancel(session_id)，避免上一轮的
       残留标记污染本轮（防御性清理）

设计要点：
- key 是 session_id（与 stream_queue 同 key），方便定位与排错
- 使用 threading.Lock 保护字典读写，避免极端竞态
- 不持久化：取消是"用户当下意图"，跨进程无意义
"""
from __future__ import annotations

import threading
from typing import Dict

# 受 _lock 保护的取消标记字典：session_id -> True/False
_cancel_flags: Dict[int, bool] = {}
_lock = threading.Lock()


def request_cancel(session_id: int) -> None:
    """请求取消：API 层在收到 /cancel 请求时调用"""
    with _lock:
        _cancel_flags[session_id] = True


def is_cancelled(session_id: int | None) -> bool:
    """节点轮询入口：True 表示用户已请求取消，节点应尽快主动退出"""
    if session_id is None:
        return False
    with _lock:
        return _cancel_flags.get(session_id, False)


def clear_cancel(session_id: int | None) -> None:
    """清除标记：每轮 chat_stream 启动 / 结束时调用，避免标记跨轮污染"""
    if session_id is None:
        return
    with _lock:
        _cancel_flags.pop(session_id, None)
