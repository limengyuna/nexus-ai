"""
LLM 客户端封装

DeepSeek API 兼容 OpenAI Chat Completions 协议，所以直接用 openai 官方 SDK，
只需替换 base_url 和 api_key 即可。

提供三种调用方式：
1. complete()            —— 同步一次性返回完整回复（用于 Router 意图判断、摘要等）
2. complete_stream()     —— 流式生成（用于对话场景，配合 SSE 推送给前端）
3. complete_with_tools() —— Function Calling（用于 Tool Agent 决定调哪个工具）
"""
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from loguru import logger
from openai import OpenAI

from app.core.config import settings


class LLMClient:
    """DeepSeek LLM 客户端封装（单例模式）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        api_key = api_key or settings.DEEPSEEK_API_KEY
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY 未配置，无法初始化 LLM 客户端。"
                "请在 .env 中设置 DEEPSEEK_API_KEY=sk-xxx"
            )

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or settings.DEEPSEEK_API_BASE,
            timeout=60.0,  # 整体超时 60s
        )
        self.model = model or settings.DEEPSEEK_MODEL
        logger.info("LLMClient 初始化完成 (model={}, base_url={})", self.model, base_url or settings.DEEPSEEK_API_BASE)

    # ---------- 一次性完整响应 ----------
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        同步调用，返回完整回复文本

        :param messages: OpenAI 格式 [{"role": "system|user|assistant", "content": "..."}]
        :param temperature: 采样温度，0 最确定，1 最发散
        :param max_tokens: 最大输出 token 数
        :param response_format: 如 {"type": "json_object"} 强制返回 JSON
        """
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        logger.debug(
            "LLM 调用完成 [{}] in={} out={} total={}",
            self.model,
            usage.prompt_tokens if usage else "?",
            usage.completion_tokens if usage else "?",
            usage.total_tokens if usage else "?",
        )
        return content

    # ---------- 流式响应（SSE 推送用） ----------
    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """
        流式调用，逐 token yield 内容片段

        典型用法::

            for chunk in llm.complete_stream(messages):
                yield f"data: {chunk}\\n\\n"  # SSE
        """
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    # ---------- Function Calling ----------
    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.3,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """
        带工具调用的 chat completion

        :param tools: OpenAI 格式的工具定义 [{"type": "function", "function": {...}}]
        :param tool_choice: "auto" / "none" / {"type": "function", "function": {"name": "xxx"}}
        :return: {"content": str, "tool_calls": list, "finish_reason": str}
        """
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
        )
        choice = resp.choices[0]
        tool_calls_raw = choice.message.tool_calls or []

        # 把 ToolCall 对象转成纯 dict，便于序列化和存到 DB
        tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,  # JSON 字符串
            }
            for tc in tool_calls_raw
        ]

        # DeepSeek thinking mode 会返回 reasoning_content，多轮对话必须传回
        reasoning_content = getattr(choice.message, "reasoning_content", None)

        return {
            "content": choice.message.content or "",
            "tool_calls": tool_calls,
            "finish_reason": choice.finish_reason,
            "reasoning_content": reasoning_content,
        }


# ---------- 单例工厂 ----------
_singleton_llm: Optional[LLMClient] = None
_singleton_llm_fast: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    """获取重型 LLM 单例（Pro 模型，用于 Tool Agent、Skills 等复杂推理）"""
    global _singleton_llm
    if _singleton_llm is None:
        _singleton_llm = LLMClient()
    return _singleton_llm


def get_llm_fast() -> LLMClient:
    """获取轻型 LLM 单例（Flash 模型，用于 Router、闲聊、RAG 等简单任务）"""
    global _singleton_llm_fast
    if _singleton_llm_fast is None:
        _singleton_llm_fast = LLMClient(model=settings.DEEPSEEK_MODEL_FAST)
    return _singleton_llm_fast


def reset_llm() -> None:
    """重置所有 LLM 单例（测试用）"""
    global _singleton_llm, _singleton_llm_fast
    _singleton_llm = None
    _singleton_llm_fast = None
