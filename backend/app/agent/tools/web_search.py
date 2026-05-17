"""
Web 搜索工具

基于 Tavily Search API（AI 专用搜索引擎，LangChain/Perplexity 等主流产品使用）。
中文搜索质量优于 DuckDuckGo，需要 API Key（免费 1000 次/月）。

注意：
- 搜索服务偶尔会限流或超时，所以对外只暴露 ok/error，
  不抛异常，让 Skill 编排可以判断后继续走 LLM
- 返回前 N 条结果（title / url / snippet 摘要）
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
    通用 web 搜索（Tavily Search API 后端）。

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
            # 延迟导入，避免启动时加载第三方库
            from tavily import TavilyClient
            from app.core.config import settings

            if not settings.TAVILY_API_KEY:
                return {
                    "ok": False,
                    "query": params.query,
                    "results": [],
                    "error": "TAVILY_API_KEY 未配置，请在 .env 中设置",
                }

            client = TavilyClient(api_key=settings.TAVILY_API_KEY)
            response = client.search(
                query=params.query,
                max_results=params.max_results,
                search_depth="basic",       # basic 更快；advanced 更深但更慢
                include_answer=False,        # 不需要 Tavily 自己的 AI 回答
            )

            results: List[Dict[str, str]] = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in response.get("results", [])
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
