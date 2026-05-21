"""
研究助手技能（Skill）—— 纯互联网调研编排

工作流：
1. LLM 把用户研究问题拆成 2-3 个搜索关键词
2. 多线程并行 web_search 搜公开互联网
3. LLM 综合 web 结果，写一份带引用的研究报告

职责边界：
- 本 Skill 只负责互联网搜索 + 综合报告，不涉及内部知识库
- 如需结合知识库，由 Supervisor 拆多步：本 Skill 做 web 搜索 + document_summarizer 做 KB 总结

亮点：
- 并行搜索：ThreadPoolExecutor 多关键词同时搜，比 FC 循环串行快 2-3 倍
- 引用标注：每段论述附 [W#] 来源标签，可溯源
- 结构化报告：Markdown 章节 + 一句话核心 + 参考链接
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from loguru import logger

from app.agent.skills.registry import BaseSkill, register_skill


@register_skill
class ResearchAssistantSkill(BaseSkill):
    """研究助手：纯互联网并行搜索 + LLM 综合写报告"""

    name = "research_assistant"
    description = (
        "针对一个研究主题做互联网调研：多关键词并行搜索公开互联网，"
        "由 LLM 综合写一份带引用的结构化研究报告。"
        "适合「调研 X 技术」「研究 Y 概念」「了解 Z 行业」等场景。"
    )
    required_tools = ["web_search"]
    trigger_keywords = [
        "研究", "调研", "了解一下", "research", "investigate", "look into",
    ]

    _MAX_QUERIES = 3              # LLM 拆出的搜索关键词最大数
    _RESULTS_PER_QUERY = 4        # 每次 web 搜索保留的结果数
    _MAX_CONTEXT_ITEMS = 12       # 喂给 LLM 综合的总条目上限

    def execute(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}

        tool_calls: List[Dict[str, Any]] = []

        # ---------- Step 1: LLM 拆解搜索关键词 ----------
        search_queries = self._llm_decompose(user_input)
        logger.info("[Skill:{}] 拆解出 {} 个搜索关键词: {}",
                    self.name, len(search_queries), search_queries)
        tool_calls.append({
            "name": "llm_decompose_queries",
            "kind": "llm",
            "arguments": {"user_input": user_input},
            "result": search_queries,
        })

        # ---------- Step 2: 并行 web 搜索（线程池，主流做法参考 Perplexity） ----------
        web_results: List[Dict[str, str]] = []  # {title, url, snippet, query}

        def _do_search(q: str) -> Dict[str, Any]:
            """单次搜索（在子线程中执行）"""
            resp = self._call_tool(
                "web_search", query=q, max_results=self._RESULTS_PER_QUERY,
            )
            return {"query": q, "resp": resp}

        with ThreadPoolExecutor(max_workers=len(search_queries)) as pool:
            futures = {pool.submit(_do_search, q): q for q in search_queries}
            for future in as_completed(futures):
                result = future.result()
                q, search_resp = result["query"], result["resp"]
                tool_calls.append({
                    "name": "web_search",
                    "kind": "tool",
                    "arguments": {"query": q, "max_results": self._RESULTS_PER_QUERY},
                    "result": (
                        f"返回 {len(search_resp.get('results', []))} 条"
                        if search_resp.get("ok") else f"失败: {search_resp.get('error')}"
                    ),
                })
                if search_resp.get("ok"):
                    for r in search_resp["results"]:
                        web_results.append({**r, "query": q})

        # 去重（按 url）
        seen_urls = set()
        deduped_web = []
        for r in web_results:
            if r["url"] and r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                deduped_web.append(r)
        deduped_web = deduped_web[: self._MAX_CONTEXT_ITEMS]

        # ---------- Step 3: 检查是否有搜索结果 ----------
        if not deduped_web:
            return {
                "answer": "调研未拿到任何资料：web 搜索失败（可能被限流），请稍后重试。",
                "tool_calls": tool_calls,
                "meta": {"skill": self.name, "web_count": 0},
            }

        # ---------- Step 4: LLM 综合写报告 ----------
        report = self._llm_compose(user_input, deduped_web)
        tool_calls.append({
            "name": "llm_compose_report",
            "kind": "llm",
            "arguments": {
                "web_count": len(deduped_web),
            },
            "result": f"输出 {len(report)} 字符研究报告",
        })

        return {
            "answer": report,
            "tool_calls": tool_calls,
            "meta": {
                "skill": self.name,
                "search_queries": search_queries,
                "web_sources": len(deduped_web),
            },
        }

    # ---------- 内部：LLM 拆解搜索关键词 ----------
    def _llm_decompose(self, user_input: str) -> List[str]:
        # 关键词拆解是轻任务，用 Flash 模型即可（参考 Perplexity 分级模型策略）
        from app.agent.llm import get_llm_fast

        llm = get_llm_fast()
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是搜索关键词优化专家。把用户的研究主题拆解为 2-3 个互补的、"
                    "适合 web 搜索引擎的关键词组合（中文优先，技术词保留英文）。"
                    "只输出 JSON 数组（字符串列表），不要任何解释。\n"
                    "示例：\n"
                    "输入：调研一下 LangGraph 的并发执行机制\n"
                    "输出：[\"LangGraph 并发执行 原理\", \"LangGraph parallel execution\", "
                    "\"LangGraph state graph 多节点 并行\"]"
                ),
            },
            {"role": "user", "content": f"研究主题：{user_input}"},
        ]
        raw = llm.complete(messages=prompt, temperature=0.3, max_tokens=200)
        try:
            start = raw.find("[")
            end = raw.rfind("]")
            if start >= 0 and end > start:
                queries = json.loads(raw[start : end + 1])
                if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                    return queries[: self._MAX_QUERIES] or [user_input]
        except Exception as e:
            logger.warning("[Skill:{}] 关键词 JSON 解析失败: {}", self.name, e)
        return [user_input]

    # ---------- 内部：LLM 综合写报告 ----------
    def _llm_compose(
        self,
        user_input: str,
        web_results: List[Dict[str, str]],
    ) -> str:
        from app.agent.llm import get_llm_fast

        # 编号 web 资料
        web_section_parts = []
        for i, r in enumerate(web_results, 1):
            web_section_parts.append(
                f"[W{i}] {r['title']}\n  URL: {r['url']}\n  摘要: {r['snippet']}"
            )
        web_section = "\n\n".join(web_section_parts) if web_section_parts else "（无 web 资料）"

        llm = get_llm_fast()
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是专业的研究分析师。根据用户提供的 web 搜索结果，"
                    "撰写一份结构清晰的研究报告，要求：\n"
                    "1. Markdown 二级标题分章节（## 章节名）\n"
                    "2. 每个论述用 `[W编号]` 标注引用来源\n"
                    "3. **不要编造未在资料中出现的引用**\n"
                    "4. 不要堆砌摘要原文，要做提炼与归纳\n"
                    "5. 末尾给一段【一句话核心】，并附上「主要参考链接」列表\n"
                    "6. 如果某些方面资料不足，明确指出"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## 研究主题\n{user_input}\n\n"
                    f"## Web 搜索结果（共 {len(web_results)} 条）\n{web_section}\n\n"
                    "请综合写一份研究报告。"
                ),
            },
        ]
        return llm.complete(messages=prompt, temperature=0.5, max_tokens=2000)
