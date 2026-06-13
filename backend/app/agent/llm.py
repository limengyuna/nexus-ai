"""
LLM 客户端封装

DeepSeek API 兼容 OpenAI Chat Completions 协议，所以直接用 openai 官方 SDK，
只需替换 base_url 和 api_key 即可。

提供三种调用方式：
1. complete()            —— 同步一次性返回完整回复（用于 Router 意图判断、摘要等）
2. complete_stream()     —— 流式生成（用于对话场景，配合 SSE 推送给前端）
3. complete_with_tools() —— Function Calling（用于 Tool Agent 决定调哪个工具）
"""
import time as _time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple

from loguru import logger
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError

from app.core.config import settings


class LLMClient:
    """DeepSeek LLM 客户端封装（单例模式）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        thinking_enabled: Optional[bool] = None,
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
        # 思考模式开关：仅影响 deepseek-v4-pro 等支持思考的模型
        self.thinking_enabled = thinking_enabled if thinking_enabled is not None else settings.DEEPSEEK_THINKING_ENABLED
        logger.info("LLMClient 初始化完成 (model={}, thinking={}, base_url={})", self.model, self.thinking_enabled, base_url or settings.DEEPSEEK_API_BASE)

    # ---------- 重试配置 ----------
    # 最大重试次数（不含首次调用，即总共最多 1 + _MAX_RETRIES 次）
    _MAX_RETRIES = 2
    # 指数退避基数（秒）：第1次重试等1秒，第2次等2秒
    _RETRY_BACKOFF_BASE = 1.0

    def _call_with_retry(self, kwargs: Dict[str, Any]) -> Any:
        """
        带重试的 LLM 调用（底层统一入口）

        仅对以下可恢复错误重试，其他错误直接抛出：
        - RateLimitError (429)：API 限流
        - APITimeoutError：请求超时
        - APIConnectionError：网络连接失败
        """
        last_exc = None
        for attempt in range(1 + self._MAX_RETRIES):
            try:
                return self._client.chat.completions.create(**kwargs)
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                last_exc = e
                if attempt < self._MAX_RETRIES:
                    wait = self._RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "[LLM 重试] {} 第{}/{}次重试，等待{:.1f}s | 错误: {}",
                        type(e).__name__, attempt + 1, self._MAX_RETRIES, wait, e,
                    )
                    _time.sleep(wait)
                else:
                    logger.error(
                        "[LLM 重试] {} 已达最大重试次数({})，放弃 | 错误: {}",
                        type(e).__name__, self._MAX_RETRIES, e,
                    )
        # 所有重试耗尽，抛出最后一个异常
        raise last_exc

    def _thinking_extra_body(self) -> Optional[Dict[str, Any]]:
        """根据思考模式开关生成 extra_body 参数"""
        if self.thinking_enabled:
            return None  # 默认开启，不需要额外参数
        return {"thinking": {"type": "disabled"}}

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
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        extra = self._thinking_extra_body()
        if extra:
            kwargs["extra_body"] = extra
        resp = self._call_with_retry(kwargs)
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

    def complete_counted(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Dict[str, int]]:
        """
        同步调用，返回 (回复文本, token 用量字典)

        用量字典格式：{"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}
        """
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        extra = self._thinking_extra_body()
        if extra:
            kwargs["extra_body"] = extra
        resp = self._call_with_retry(kwargs)
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }
        logger.debug(
            "LLM 调用完成 [{}] in={} out={} total={}",
            self.model, usage_dict["prompt_tokens"], usage_dict["completion_tokens"], usage_dict["total_tokens"],
        )
        return content, usage_dict

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
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        extra = self._thinking_extra_body()
        if extra:
            kwargs["extra_body"] = extra
        stream = self._call_with_retry(kwargs)
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
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
        )
        extra = self._thinking_extra_body()
        if extra:
            kwargs["extra_body"] = extra
        resp = self._call_with_retry(kwargs)
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

        usage = resp.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }

        return {
            "content": choice.message.content or "",
            "tool_calls": tool_calls,
            "finish_reason": choice.finish_reason,
            "reasoning_content": reasoning_content,
            "usage": usage_dict,
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
