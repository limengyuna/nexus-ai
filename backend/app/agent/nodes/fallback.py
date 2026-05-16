"""
闲聊 / 兜底节点（双重职责）

1. 当 Router 决策为 chitchat 时，正常处理闲聊
2. 当其他节点抛错（被 graph.py 捕获）时，作为 fallback 输出友好兜底回复

设计为简单的单 LLM 调用 + 历史摘要注入。
"""
import time
from typing import Any, Dict

from loguru import logger

from app.agent.llm import get_llm
from app.agent.state import AgentState, append_trace

_CHITCHAT_SYSTEM_PROMPT = """你是 NexusAI 智能助手。

身份与边界：
- 当用户问候、闲聊、问常识或问你是谁时，简洁友好地回答
- 当用户问的问题需要查知识库才能回答时，提示"如需查询知识库内容，请在创建对话时关联知识库"
- 当用户问的问题需要工具支持时，提示"我可以帮你查天气、做计算、规划旅行等，请详细描述需求"

回答风格：简洁、友好、中文。"""


def fallback_node(state: AgentState) -> Dict[str, Any]:
    """闲聊 / 兜底节点"""
    started_at = time.time()
    user_input = state.get("user_input", "")
    summary = state.get("summary", "")
    prev_error = state.get("error")

    messages = [{"role": "system", "content": _CHITCHAT_SYSTEM_PROMPT}]
    if summary:
        messages.append({
            "role": "system",
            "content": f"以下是历史对话摘要，仅供参考：\n{summary}",
        })
    messages.append({"role": "user", "content": user_input})

    llm = get_llm()
    try:
        answer = llm.complete(messages=messages, temperature=0.6, max_tokens=400)
    except Exception as e:
        logger.exception("[Fallback] 连 LLM 也失败了: {}", e)
        answer = "抱歉，我暂时无法处理这个请求，请稍后再试。"

    # 如果是因为前置节点报错而进 fallback，把错误信息带出
    if prev_error:
        answer = f"（前置处理出错：{prev_error}）\n\n{answer}"

    return {
        "final_answer": answer,
        "execution_trace": append_trace(
            state, "fallback", started_at,
            input_summary={
                "user_input": user_input[:60],
                "has_summary": bool(summary),
                "prev_error": prev_error,
            },
            output_summary={"answer_preview": answer[:80]},
        ),
    }
