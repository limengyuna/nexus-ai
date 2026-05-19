"""
文档摘要技能（Skill）

工作流（双模式）：
A. 主题总结模式（默认）：
   1. LLM 把用户问题“拆解”成 1-3 个检索子查询（multi-query 提升召回多样性）
   2. 对每个子查询调用 rag_search Tool，去重合并 chunks
   3. 用专门设计的 prompt，让 LLM 综合所有 chunks 写一份带小标题 + 引用的总结

B. 全文总结模式（用户要求总结整篇/全文时触发）：
   1. 按 document_id 拉取某篇文档的全部 chunk（不依赖向量检索）
   2. Map-Reduce：先对每批 chunk 生成局部摘要，再综合所有局部摘要写最终总结

亮点：
- 真正的“多 Tool + 多步 LLM 编排”：N 次 rag_search + 2 次 LLM
- 复用阶段二的 RAG 管道（无需新依赖）
- 结果带“信息来源”，避免幻觉
- 与知识库联动：调用时必须传 kb_id（从 context 拿）
- 有 KB 时也允许关键词匹配触发（allow_with_kb = True）
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
    allow_with_kb = True  # 有 KB 时也允许关键词匹配触发

    # 每个子查询的 top_k（控制成本）
    _TOP_K_PER_QUERY = 5
    # 最多检索子查询数量（避免 LLM 拆得太多）
    _MAX_SUB_QUERIES = 3
    # 喂给 LLM 综合的 chunks 上限（避免 context 爆掉）
    _MAX_CHUNKS_FOR_COMPOSE = 10
    # Map-Reduce 每批处理的 chunk 数量
    _MAP_BATCH_SIZE = 6

    # 全文总结触发关键词（用户输入包含这些词时走全文模式）
    _FULL_DOC_KEYWORDS = [
        "全文", "整篇", "这篇文档", "这个文档", "整个文档", "全部内容",
        "这篇论文", "整篇论文", "全篇",
    ]

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

        # ---------- 路由：判断走全文总结还是主题总结 ----------
        if self._is_full_doc_request(user_input):
            logger.info("[Skill:{}] 检测到全文总结请求，走 Map-Reduce 模式", self.name)
            return self._execute_full_doc(user_input, kb_id)
        else:
            logger.info("[Skill:{}] 走主题总结模式（multi-query）", self.name)
            return self._execute_topic(user_input, kb_id)

    # ==========================================================
    # 模式 A：主题总结（multi-query 检索）
    # ==========================================================
    def _execute_topic(self, user_input: str, kb_id: int) -> Dict[str, Any]:
        """主题总结：multi-query 检索 + LLM 综合"""
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
                "result": f"返回 {len(chunks)} 个分块",
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
        merged_chunks.sort(key=lambda c: c["score"])
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
                "mode": "topic",
                "kb_id": kb_id,
                "sub_queries": sub_queries,
                "total_chunks_retrieved": len(merged_chunks),
                "chunks_used_for_summary": len(top_chunks),
            },
        }

    # ==========================================================
    # 模式 B：全文总结（按 document_id 拉取全部 chunk + Map-Reduce）
    # ==========================================================
    def _execute_full_doc(self, user_input: str, kb_id: int) -> Dict[str, Any]:
        """全文总结：拉取文档全部 chunk，Map-Reduce 生成摘要"""
        from app.core.database import SessionLocal
        from app.models.document import Document, DocumentStatus
        from app.models.knowledge_base import KnowledgeBase
        from app.rag.vector_store import get_vector_store

        tool_calls: List[Dict[str, Any]] = []

        # 查询该知识库下所有已完成的文档
        db = SessionLocal()
        try:
            kb = db.get(KnowledgeBase, kb_id)
            if kb is None or not kb.collection_name:
                return {
                    "answer": f"知识库 #{kb_id} 不存在或未初始化。",
                    "tool_calls": [],
                    "meta": {"skill": self.name, "error": "kb_missing"},
                }
            collection_name = kb.collection_name

            # 获取知识库里的文档列表（只取已完成的）
            docs = (
                db.query(Document)
                .filter(Document.kb_id == kb_id, Document.status == DocumentStatus.COMPLETED)
                .order_by(Document.id)
                .all()
            )
            if not docs:
                return {
                    "answer": "该知识库中没有已处理完成的文档。",
                    "tool_calls": [],
                    "meta": {"skill": self.name, "kb_id": kb_id, "found": 0},
                }

            # 如果只有一篇文档，直接用它；多篇则取第一篇（后续可扩展为让 LLM 选择）
            target_doc = docs[0]
            if len(docs) > 1:
                # 简单策略：用向量检索找到最相关的文档
                target_doc = self._find_most_relevant_doc(docs, user_input, kb_id)

            logger.info("[Skill:{}] 全文总结目标文档: id={} name={}",
                        self.name, target_doc.id, target_doc.file_name)
        finally:
            db.close()

        # 按 document_id 拉取该文档的全部 chunk（不依赖向量检索）
        vector_store = get_vector_store()
        all_hits = vector_store.list_by_metadata(
            collection_name=collection_name,
            where={"document_id": target_doc.id},
        )
        tool_calls.append({
            "name": "list_by_metadata",
            "kind": "tool",
            "arguments": {"collection": collection_name, "document_id": target_doc.id},
            "result": f"拉取文档 '{target_doc.file_name}' 全部 {len(all_hits)} 个分块",
        })

        if not all_hits:
            return {
                "answer": f"文档 '{target_doc.file_name}' 在向量库中没有找到分块数据。",
                "tool_calls": tool_calls,
                "meta": {"skill": self.name, "kb_id": kb_id, "document_id": target_doc.id},
            }

        # 按 chunk_index 排序，保持原文顺序
        all_chunks = [
            {"chunk_id": h.chunk_id, "content": h.content, "metadata": h.metadata}
            for h in all_hits
        ]

        # ---------- Map-Reduce ----------
        if len(all_chunks) <= self._MAX_CHUNKS_FOR_COMPOSE:
            # chunk 数量不多，直接综合（无需 Map 阶段）
            summary = self._llm_compose(user_input, all_chunks)
            tool_calls.append({
                "name": "llm_compose_summary",
                "kind": "llm",
                "arguments": {"chunks_count": len(all_chunks)},
                "result": f"直接综合，输出 {len(summary)} 字符摘要",
            })
        else:
            # Map 阶段：分批生成局部摘要
            partial_summaries = []
            for batch_start in range(0, len(all_chunks), self._MAP_BATCH_SIZE):
                batch = all_chunks[batch_start:batch_start + self._MAP_BATCH_SIZE]
                partial = self._llm_map_summarize(batch)
                partial_summaries.append(partial)
                logger.debug("[Skill:{}] Map 批次 {}: {} chunks → {} 字符",
                            self.name, batch_start // self._MAP_BATCH_SIZE + 1,
                            len(batch), len(partial))

            tool_calls.append({
                "name": "llm_map_summarize",
                "kind": "llm",
                "arguments": {"total_chunks": len(all_chunks), "batches": len(partial_summaries)},
                "result": f"生成 {len(partial_summaries)} 段局部摘要",
            })

            # Reduce 阶段：综合所有局部摘要写最终总结
            summary = self._llm_reduce(user_input, partial_summaries)
            tool_calls.append({
                "name": "llm_reduce_summary",
                "kind": "llm",
                "arguments": {"partial_count": len(partial_summaries)},
                "result": f"Reduce 输出 {len(summary)} 字符最终摘要",
            })

        return {
            "answer": summary,
            "tool_calls": tool_calls,
            "meta": {
                "skill": self.name,
                "mode": "full_doc",
                "kb_id": kb_id,
                "document_id": target_doc.id,
                "document_name": target_doc.file_name,
                "total_chunks": len(all_chunks),
            },
        }

    # ==========================================================
    # 辅助方法
    # ==========================================================
    def _is_full_doc_request(self, user_input: str) -> bool:
        """判断用户是否要求总结整篇文档"""
        lower = user_input.lower()
        return any(kw in lower for kw in self._FULL_DOC_KEYWORDS)

    def _find_most_relevant_doc(self, docs, user_input: str, kb_id: int):
        """多文档时，用简单检索找到最相关的文档"""
        try:
            chunks = self._call_tool("rag_search", kb_id=kb_id, query=user_input, top_k=1)
            if chunks:
                hit_doc_id = chunks[0]["metadata"].get("document_id")
                for doc in docs:
                    if doc.id == hit_doc_id:
                        return doc
        except Exception as e:
            logger.warning("[Skill:{}] 文档匹配失败，使用第一篇: {}", self.name, e)
        return docs[0]

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

    # ---------- 内部：Map 阶段——对一批 chunk 生成局部摘要 ----------
    def _llm_map_summarize(self, chunks: List[Dict[str, Any]]) -> str:
        """Map 阶段：对一批 chunk 提取关键信息，生成局部摘要"""
        from app.agent.llm import get_llm

        text_parts = []
        for i, c in enumerate(chunks, 1):
            text_parts.append(f"[片段 {i}]\n{c['content']}")
        text_block = "\n\n".join(text_parts)

        llm = get_llm()
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是文档摘要助手。请阅读下面的文档片段，提取其中的关键信息，"
                    "生成一段简洁的中文摘要（200-400字）。\n"
                    "要求：\n"
                    "1. 保留核心事实、数据、结论\n"
                    "2. 去除冗余和重复内容\n"
                    "3. 保持信息的准确性，不要编造"
                ),
            },
            {
                "role": "user",
                "content": f"请摘要以下内容：\n\n{text_block}",
            },
        ]
        return llm.complete(messages=prompt, temperature=0.3, max_tokens=600)

    # ---------- 内部：Reduce 阶段——综合所有局部摘要写最终总结 ----------
    def _llm_reduce(self, user_input: str, partial_summaries: List[str]) -> str:
        """Reduce 阶段：综合所有局部摘要，生成最终的结构化总结"""
        from app.agent.llm import get_llm

        parts_text = "\n\n---\n\n".join(
            f"[局部摘要 {i}]\n{s}" for i, s in enumerate(partial_summaries, 1)
        )

        llm = get_llm()
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是专业的资料综合分析师。下面给出的是同一篇文档不同部分的局部摘要，"
                    "请综合所有局部摘要，撰写一份**完整、结构清晰**的中文总结。\n"
                    "要求：\n"
                    "1. 用 Markdown 二级标题分章节（## 章节名）\n"
                    "2. 合并重复信息，保留所有关键要点\n"
                    "3. 不要堆砌原文，要做提炼与归纳\n"
                    "4. 末尾给一段【一句话核心】\n"
                    "5. 如果某些方面信息不足，直接说明"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## 用户问题\n{user_input}\n\n"
                    f"## 局部摘要（共 {len(partial_summaries)} 段）\n{parts_text}\n\n"
                    "请综合写一份最终总结。"
                ),
            },
        ]
        return llm.complete(messages=prompt, temperature=0.4, max_tokens=1500)
