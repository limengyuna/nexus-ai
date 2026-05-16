"""
文档摘要技能（Skill）

工作流：
1. LLM 把用户问题"拆解"成 1-3 个检索子查询（multi-query 提升召回多样性）
2. 对每个子查询调用 rag_search Tool，去重合并 chunks
3. 用专门设计的 prompt，让 LLM 综合所有 chunks 写一份带小标题 + 引用的总结

亮点：
- 真正的"多 Tool + 多步 LLM 编排"：N 次 rag_search + 2 次 LLM
- 复用阶段二的 RAG 管道（无需新依赖）
- 结果带"信息来源"，避免幻觉
- 与知识库联动：调用时必须传 kb_id（从 context 拿）
"""
import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from app.agent.skills.registry import BaseSkill, register_skill


@register_skill
class DocumentSummarizerSkill(BaseSkill):
    """文档摘要技能：multi-query RAG 检索 + LLM 综合总结"""

    name = "document_summarizer"
    description = (
        "针对已关联的知识库做智能摘要。会先把用户问题拆成多个检索子查询，"
        "用 RAG 拿到原始证据，再综合写出带小标题与引用的总结。"
        "适合「总结这篇文档」「概括这个项目的架构」「归纳第三章的要点」等场景。"
    )
    required_tools = ["rag_search"]
    trigger_keywords = [
        "总结", "摘要", "概括", "归纳", "简介", "summarize", "summary", "overview",
    ]

    # 每个子查询的 top_k（控制成本）
    _TOP_K_PER_QUERY = 5
    # 最多检索子查询数量（避免 LLM 拆得太多）
    _MAX_SUB_QUERIES = 3
    # 喂给 LLM 综合的 chunks 上限（避免 context 爆掉）
    _MAX_CHUNKS_FOR_COMPOSE = 10

    def execute(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        kb_id: Optional[int] = context.get("kb_id")

        # ---------- 0. 必须关联知识库 ----------
        if kb_id is None:
            return {
                "answer": (
                    "请先关联一个知识库再使用文档摘要技能。\n\n"
                    "你可以在创建会话时选择关联的知识库；或在 Skills 测试页输入框中"
                    "用 `[kb_id=1] 你的问题` 的格式手动指定（仅测试用）。"
                ),
                "tool_calls": [],
                "meta": {"skill": self.name, "missing": "kb_id"},
            }

        # 允许测试时用 [kb_id=N] 前缀覆盖
        m = re.match(r"^\s*\[kb_id=(\d+)\]\s*(.*)$", user_input)
        if m:
            kb_id = int(m.group(1))
            user_input = m.group(2)

        tool_calls: List[Dict[str, Any]] = []

        # ---------- 1. LLM 拆解为多个检索子查询 ----------
        sub_queries = self._llm_decompose(user_input)
        logger.info("[Skill:{}] 拆解出 {} 个子查询: {}", self.name, len(sub_queries), sub_queries)
        tool_calls.append({
            "name": "llm_decompose",
            "kind": "llm",
            "arguments": {"user_input": user_input},
            "result": sub_queries,
        })

        # ---------- 2. 多次 RAG 检索 + 去重合并 ----------
        seen_chunk_ids: set = set()
        merged_chunks: List[Dict[str, Any]] = []
        for q in sub_queries:
            chunks = self._call_tool(
                "rag_search", kb_id=kb_id, query=q, top_k=self._TOP_K_PER_QUERY,
            )
            tool_calls.append({
                "name": "rag_search",
                "kind": "tool",
                "arguments": {"kb_id": kb_id, "query": q, "top_k": self._TOP_K_PER_QUERY},
                "result": f"返回 {len(chunks)} 个分块",  # 全文太长，仅 trace 摘要
            })
            for c in chunks:
                if c["chunk_id"] in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(c["chunk_id"])
                merged_chunks.append(c)

        if not merged_chunks:
            return {
                "answer": "在该知识库中没有找到与你问题相关的内容，可能该知识库未包含相关文档。",
                "tool_calls": tool_calls,
                "meta": {"skill": self.name, "kb_id": kb_id, "found": 0},
            }

        # 取最高 score 的前 N 条喂给 LLM 综合
        merged_chunks.sort(key=lambda c: c["score"])  # cosine 距离越小越相似
        top_chunks = merged_chunks[: self._MAX_CHUNKS_FOR_COMPOSE]

        # ---------- 3. LLM 综合写总结 ----------
        summary = self._llm_compose(user_input, top_chunks)
        tool_calls.append({
            "name": "llm_compose_summary",
            "kind": "llm",
            "arguments": {"chunks_count": len(top_chunks)},
            "result": f"输出 {len(summary)} 字符摘要",
        })

        return {
            "answer": summary,
            "tool_calls": tool_calls,
            "meta": {
                "skill": self.name,
                "kb_id": kb_id,
                "sub_queries": sub_queries,
                "total_chunks_retrieved": len(merged_chunks),
                "chunks_used_for_summary": len(top_chunks),
            },
        }

    # ---------- 内部：LLM 拆解子查询 ----------
    def _llm_decompose(self, user_input: str) -> List[str]:
        """让 LLM 把用户的"宽问题"拆成几个更精确的检索子查询"""
        from app.agent.llm import get_llm

        llm = get_llm()
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是检索查询优化专家。把用户的摘要请求拆解为 1-3 个互补的、"
                    "适合向量检索的精确子查询，覆盖不同侧面。"
                    "只输出 JSON 数组（字符串列表），不要任何解释。\n"
                    "示例：\n"
                    "输入：总结这个项目的架构\n"
                    "输出：[\"项目整体架构设计\", \"核心模块与技术栈\", \"模块之间的协作关系\"]"
                ),
            },
            {"role": "user", "content": f"用户问题：{user_input}"},
        ]
        raw = llm.complete(messages=prompt, temperature=0.2, max_tokens=200)
        # 尽力从输出中抓 JSON
        try:
            # 找到第一个 [ 和最后一个 ]
            start = raw.find("[")
            end = raw.rfind("]")
            if start >= 0 and end > start:
                queries = json.loads(raw[start : end + 1])
                if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                    return queries[: self._MAX_SUB_QUERIES] or [user_input]
        except Exception as e:
            logger.warning("[Skill:{}] 子查询 JSON 解析失败，回退到原问题: {}", self.name, e)
        # 兜底
        return [user_input]

    # ---------- 内部：LLM 综合摘要 ----------
    def _llm_compose(self, user_input: str, chunks: List[Dict[str, Any]]) -> str:
        """基于检索到的 chunks 写综合摘要"""
        from app.agent.llm import get_llm

        # 组装参考资料文本，给每段编号便于引用
        refs = []
        for i, c in enumerate(chunks, 1):
            src = c["metadata"].get("file_name", "未知来源")
            refs.append(f"[{i}] 《{src}》\n{c['content']}")
        refs_text = "\n\n---\n\n".join(refs)

        llm = get_llm()
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是专业的资料综合分析师。基于用户提供的参考资料编号片段，"
                    "撰写一份**结构清晰**的中文总结，要求：\n"
                    "1. 用 Markdown 二级标题分章节（## 章节名）\n"
                    "2. 每个论述后用 `[编号]` 注明引用来源（如 `[1][3]`），不要编造未出现的引用\n"
                    "3. 不要堆砌原文，要做提炼与归纳\n"
                    "4. 末尾给一段【一句话核心】\n"
                    "5. 如果资料不足以回答某些方面，直接说明"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## 用户问题\n{user_input}\n\n"
                    f"## 参考资料（共 {len(chunks)} 段）\n{refs_text}\n\n"
                    "请综合写一份总结。"
                ),
            },
        ]
        return llm.complete(messages=prompt, temperature=0.4, max_tokens=1500)
