"""
Web 搜索工具

基于 ddgs 库（原 duckduckgo-search，免 API key），失败时优雅降级。

注意：
- 搜索服务偶尔会限流或超时，所以对外只暴露 ok/error，
  不抛异常，让 Skill 编排可以判断后继续走 LLM
- 返回前 N 条结果（title / url / body 摘要）
- 不抓正文，避免单次响应过长（如要抓正文可以另起一个 fetch_url Tool）
"""
from typing import Any, Dict, List

from loguru import logger
from pydantic import BaseModel, Field

from app.agent.tools.registry import BaseTool, register_tool


class WebSearchArgs(BaseModel):
    """Web 搜索参数"""
    query: str = Field(..., description="要搜索的关键词或问题")
    max_results: int = Field(default=5, ge=1, le=15, description="返回结果数量")


@register_tool
class WebSearchTool(BaseTool):
    """
    通用 web 搜索（DuckDuckGo 后端，免 API key）。

    返回结构示例:
        {
          "ok": true,
          "query": "...",
          "results": [
            {"title": "...", "url": "...", "snippet": "..."},
            ...
          ],
          "error": null
        }
    """
    name = "web_search"
    description = (
        "在公开互联网上搜索信息，返回相关网页的标题/URL/摘要。"
        "适用于：查询时效性信息、调研新概念、补充内部知识库没有的内容。"
        "注意：仅返回结果摘要，不抓正文。"
    )
    args_schema = WebSearchArgs

    def run(self, **kwargs) -> Dict[str, Any]:
        params = WebSearchArgs(**kwargs)
        try:
            # 延迟导入，避免启动时连第三方库
            from ddgs import DDGS

            # ddgs v9+ API：text() 返回 list[dict]，不再需要 context manager
            raw_results = DDGS().text(
                params.query,
                max_results=params.max_results,
            )
            results: List[Dict[str, str]] = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", "") or r.get("url", ""),
                    "snippet": r.get("body", "") or r.get("snippet", ""),
                }
                for r in raw_results
            ]

            logger.debug("[web_search] query={!r} -> {} 条", params.query, len(results))
            return {
                "ok": True,
                "query": params.query,
                "results": results,
                "error": None,
            }
        except Exception as e:
            logger.warning("[web_search] 失败: {}", e)
            return {
                "ok": False,
                "query": params.query,
                "results": [],
                "error": f"{type(e).__name__}: {e}",
            }
