"""
研究助手技能（Skill）—— 最综合的编排示例

工作流：
1. LLM 把用户研究问题拆成 2-3 个搜索关键词
2. 多次 web_search 搜公开互联网
3. （可选）如果用户传了 kb_id，同步用 rag_search 查内部知识库
4. LLM 综合 web 结果 + 内部资料，写一份带引用的研究报告

亮点：
- 真正多 Tool 编排：web_search × N + rag_search × M + LLM × 2
- 优雅降级：web_search 失败时仍能基于 LLM 已知知识 + 内部 KB 输出
- 引用标注：每段论述附 [W#] (web) 或 [R#] (RAG) 来源标签
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from loguru import logger

from app.agent.skills.registry import BaseSkill, register_skill


@register_skill
class ResearchAssistantSkill(BaseSkill):
    """研究助手：web 搜索 + 内部 RAG + LLM 综合写报告"""

    name = "research_assistant"
    description = (
        "针对一个研究主题做综合调研：在公开互联网搜索，"
        "（可选）结合内部知识库，由 LLM 综合写一份带引用的研究报告。"
        "适合「调研 X 技术」「研究 Y 概念」「了解 Z 行业」等场景。"
    )
    # rag_search 是可选的（用户没传 kb_id 时跳过），web_search 是核心
    required_tools = ["web_search"]
    trigger_keywords = [
        "研究", "调研", "了解一下", "research", "investigate", "look into",
    ]

    _MAX_QUERIES = 3              # LLM 拆出的搜索关键词最大数
    _RESULTS_PER_QUERY = 4        # 每次 web 搜索保留的结果数
    _RAG_TOP_K = 5                # 内部 RAG 检索数
    _MAX_CONTEXT_ITEMS = 12       # 喂给 LLM 综合的总条目上限

    def execute(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        kb_id: Optional[int] = context.get("kb_id")  # 可选：传了就同步查内部 KB

        # 测试时支持 [kb_id=N] 前缀
        m = re.match(r"^\s*\[kb_id=(\d+)\]\s*(.*)$", user_input)
        if m:
            kb_id = int(m.group(1))
            user_input = m.group(2)

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

        # ---------- Step 3: 可选：内部 RAG 检索 ----------
        rag_chunks: List[Dict[str, Any]] = []
        if kb_id is not None:
            for q in search_queries:
                chunks = self._call_tool(
                    "rag_search", kb_id=kb_id, query=q, top_k=self._RAG_TOP_K,
                )
                tool_calls.append({
                    "name": "rag_search",
                    "kind": "tool",
                    "arguments": {"kb_id": kb_id, "query": q, "top_k": self._RAG_TOP_K},
                    "result": f"返回 {len(chunks)} 个分块",
                })
                rag_chunks.extend(chunks)
            # 去重 by chunk_id
            seen_chunk_ids = set()
            deduped_rag = []
            for c in rag_chunks:
                if c["chunk_id"] not in seen_chunk_ids:
                    seen_chunk_ids.add(c["chunk_id"])
                    deduped_rag.append(c)
            deduped_rag.sort(key=lambda c: c["score"])  # cosine 距离越小越相似
            rag_chunks = deduped_rag[: self._MAX_CONTEXT_ITEMS]

        # ---------- Step 4: 检查是否有任何信源 ----------
        if not deduped_web and not rag_chunks:
            return {
                "answer": (
                    "调研未拿到任何资料：web 搜索失败（可能被限流）"
                    "且未关联内部知识库。请稍后重试，或选择一个知识库提供内部资料。"
                ),
                "tool_calls": tool_calls,
                "meta": {"skill": self.name, "web_count": 0, "rag_count": 0},
            }

        # ---------- Step 5: LLM 综合写报告 ----------
        report = self._llm_compose(user_input, deduped_web, rag_chunks)
        tool_calls.append({
            "name": "llm_compose_report",
            "kind": "llm",
            "arguments": {
                "web_count": len(deduped_web),
                "rag_count": len(rag_chunks),
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
                "rag_sources": len(rag_chunks),
                "kb_id": kb_id,
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
        rag_chunks: List[Dict[str, Any]],
    ) -> str:
        from app.agent.llm import get_llm

        # 编号 web 资料
        web_section_parts = []
        for i, r in enumerate(web_results, 1):
            web_section_parts.append(
                f"[W{i}] {r['title']}\n  URL: {r['url']}\n  摘要: {r['snippet']}"
            )
        web_section = "\n\n".join(web_section_parts) if web_section_parts else "（无 web 资料）"

        # 编号 RAG 资料
        rag_section_parts = []
        for i, c in enumerate(rag_chunks, 1):
            src = c["metadata"].get("file_name", "未知来源")
            rag_section_parts.append(f"[R{i}] 《{src}》\n{c['content']}")
        rag_section = "\n\n---\n\n".join(rag_section_parts) if rag_section_parts else "（无内部资料）"

        llm = get_llm()
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是专业的研究分析师。根据用户提供的 web 搜索结果和（可选）内部知识库分块，"
                    "撰写一份结构清晰的研究报告，要求：\n"
                    "1. Markdown 二级标题分章节（## 章节名）\n"
                    "2. 每个论述用 `[W编号]`（web 来源）或 `[R编号]`（内部资料）标注引用\n"
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
                    f"## 内部知识库资料（共 {len(rag_chunks)} 段）\n{rag_section}\n\n"
                    "请综合写一份研究报告。"
                ),
            },
        ]
        return llm.complete(messages=prompt, temperature=0.5, max_tokens=2000)
