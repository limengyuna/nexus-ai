"""
对话 API 路由

接口设计：
- POST   /chat/sessions                创建会话
- GET    /chat/sessions                列出当前用户的会话
- GET    /chat/sessions/{id}           获取会话详情（含历史消息）
- DELETE /chat/sessions/{id}           删除会话
- POST   /chat/sessions/{id}/messages  发送消息，一次性返回 Agent 完整回复（含思考过程）
- GET    /chat/sessions/{id}/stream    流式获取会话消息

阶段四会增加 SSE 流式接口；本阶段先用同步接口，便于测试 Agent 链路。
"""
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import LIMIT_LLM, limiter
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSessionUpdate,
)
from app.schemas.common import ApiResponse
from app.services.chat_service import ChatService
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post(
    "/sessions",
    response_model=ApiResponse[ChatSessionOut],
    summary="创建对话会话",
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.kb_id is not None:
        if KnowledgeBaseService.get(db, payload.kb_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"指定的知识库 {payload.kb_id} 不存在",
            )
    session = ChatService.create_session(
        db, user_id=current_user.id, title=payload.title, kb_id=payload.kb_id,
    )
    return ApiResponse.ok(data=ChatSessionOut.model_validate(session), message="会话已创建")


@router.get(
    "/sessions",
    response_model=ApiResponse[List[ChatSessionOut]],
    summary="列出当前用户的全部会话",
)
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = ChatService.list_sessions(db, user_id=current_user.id)
    return ApiResponse.ok(data=[ChatSessionOut.model_validate(s) for s in sessions])


@router.get(
    "/sessions/{session_id}/messages",
    response_model=ApiResponse[List[ChatMessageOut]],
    summary="获取会话的所有消息",
)
def list_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatService.get_session(db, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    messages = ChatService.list_messages(db, session_id)
    return ApiResponse.ok(data=[ChatMessageOut.model_validate(m) for m in messages])


@router.patch(
    "/sessions/{session_id}",
    response_model=ApiResponse[ChatSessionOut],
    summary="更新会话（标题/关联知识库）",
)
def update_session(
    session_id: int,
    payload: ChatSessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatService.get_session(db, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    updated = ChatService.update_session(
        db, session, title=payload.title, kb_id=payload.kb_id,
    )
    return ApiResponse.ok(data=ChatSessionOut.model_validate(updated), message="会话已更新")


@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResponse[None],
    summary="删除会话",
)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatService.get_session(db, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    ChatService.delete_session(db, session)
    return ApiResponse.ok(message="会话已删除")


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ApiResponse[ChatResponse],
    summary="发送消息，触发 Agent 处理",
)
@limiter.limit(LIMIT_LLM)
def send_message(
    request: Request,  # slowapi 装饰器要求第一个参数是 request
    session_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    发送一条用户消息，触发完整的多 Agent 协作链路：

    Router → (RAG / Tool / Fallback) → 返回回复

    响应同时包含完整的"思考过程"（execution_trace），便于前端展示。
    """
    session = ChatService.get_session(db, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    try:
        assistant_msg, final_state = ChatService.chat_once(db, session, payload.message)
    except Exception as e:
        # 主图异常一般不会到这（已被 fallback 接住），但兜底一下
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent 执行失败: {e}",
        )

    return ApiResponse.ok(
        data=ChatResponse(
            message=ChatMessageOut.model_validate(assistant_msg),
            intent=final_state.get("intent", ""),
            route_reason=final_state.get("route_reason", ""),
            skill_used=final_state.get("skill_used"),
            tool_calls=final_state.get("tool_calls", []),
            retrieved_docs=final_state.get("retrieved_docs", []),
            execution_trace=final_state.get("execution_trace", []),
        )
    )


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="发送消息（SSE 流式）—— 实时返回打字机效果",
)
@limiter.limit(LIMIT_LLM)
async def stream_message(
    request: Request,
    session_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SSE 流式版本。事件类型：
    - status   : 阶段状态（user_saved / thinking）
    - meta     : Router 决策（intent / route_reason / skill_used）
    - chunk    : 回答的一段字符
    - done     : 完整元数据（含 execution_trace / retrieved_docs / token_usage）

    前端用 EventSource / fetch+ReadableStream 消费。

    ⚠️ 实现要点：FastAPI 的 Depends(get_db) 在路由函数返回 StreamingResponse 时
    会立刻执行 finally 关闭 session。所以这里只用 db 做权限校验，真正流式生成时
    必须在 generator 内部新开独立 session（用 SessionLocal）。
    """
    # 1. 用 Depends 注入的 db 做权限校验（路由返回前 db 还活着）
    session = ChatService.get_session(db, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 2. 提取流式生成时需要的纯标量，避免在 generator 内引用已 detach 的 ORM 对象
    target_session_id = session.id
    target_user_id = current_user.id
    user_message = payload.message

    async def event_generator():
        # 关键：在 generator 内部开新 db session，独立于 FastAPI Depends 的生命周期
        from app.core.database import SessionLocal

        local_db = SessionLocal()
        try:
            # 用新 session 重新加载 ChatSession ORM 对象
            local_session = ChatService.get_session(local_db, target_session_id)
            if local_session is None or local_session.user_id != target_user_id:
                err = json.dumps({"message": "会话不存在或无权访问", "type": "NotFound"})
                yield f"event: error\ndata: {err}\n\n"
                return

            async for event_type, data in ChatService.chat_stream(local_db, local_session, user_message):
                # SSE 协议格式：event: <type>\ndata: <json>\n\n
                payload_json = json.dumps(data, ensure_ascii=False, default=str)
                yield f"event: {event_type}\ndata: {payload_json}\n\n"
        except Exception as e:
            # 任何异常都包装成 error 事件，前端可统一处理
            err_payload = json.dumps({"message": str(e), "type": type(e).__name__})
            yield f"event: error\ndata: {err_payload}\n\n"
        finally:
            local_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 让 nginx 等不要缓冲
        },
    )
