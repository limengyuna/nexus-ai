"""
文档处理异步任务

完整管道：解析 → 分块 → 向量化 → 入库，并实时更新 TaskRecord 进度。

进度阶段分布：
- 10%  文件读取完成
- 30%  解析完成
- 50%  分块完成
- 90%  向量化完成
- 100% 入库完成
"""
import time
from typing import List

from loguru import logger

from app.core.database import SessionLocal
from app.models.document import DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.task import TaskStatus
from app.rag.embedder import get_embedder
from app.rag.parser import parse_document
from app.rag.splitter import get_splitter
from app.rag.vector_store import get_vector_store
from app.services.document_service import DocumentService, TaskService
from app.tasks.celery_app import celery_app


@celery_app.task(
    name="document.process",
    bind=True,
    autoretry_for=(ConnectionError,),  # 连接错误自动重试
    retry_kwargs={"max_retries": 2, "countdown": 5},
)
def process_document(self, document_id: int, task_record_id: int) -> dict:
    """
    文档处理主任务

    :param document_id: 文档 ID
    :param task_record_id: 任务记录 ID（用于回传进度）
    :return: 摘要信息字典
    """
    start_ts = time.time()
    logger.info(
        "[Task] 开始处理文档 document_id={} task_record_id={} celery_id={}",
        document_id, task_record_id, self.request.id,
    )

    # 每个 Celery 任务独立的 DB Session，避免跨任务复用
    db = SessionLocal()
    try:
        document = DocumentService.get(db, document_id)
        if document is None:
            raise ValueError(f"文档不存在: id={document_id}")

        kb = db.get(KnowledgeBase, document.kb_id)
        if kb is None:
            raise ValueError(f"知识库不存在: id={document.kb_id}")
        if not kb.collection_name:
            raise ValueError(f"知识库 {kb.id} 未初始化 collection_name")

        # ---------- 阶段 1：开始 ----------
        TaskService.update_progress(
            db, task_record_id, progress=5, status=TaskStatus.RUNNING,
        )
        DocumentService.update_status(db, document_id, DocumentStatus.PARSING)

        # ---------- 阶段 2：解析 ----------
        logger.info("[Task] 解析文档 {} ({})", document.file_name, document.file_path)
        text = parse_document(document.file_path)
        TaskService.update_progress(db, task_record_id, progress=20)

        # ---------- 阶段 2.5（可选）：LLM 清洗 ----------
        # 启用后会调用 LLM 把"伪 Markdown"重排为标准 Markdown，
        # 失败的段落自动回退原文，保证主管道不会因 LLM 问题中断
        # 文档级开关优先；为 None 则回退 KB 默认
        effective_enable_llm_clean = (
            document.enable_llm_clean
            if document.enable_llm_clean is not None
            else kb.enable_llm_clean
        )
        if effective_enable_llm_clean:
            logger.info(
                "[Task] 启用 LLM 清洗 document_id={}（doc={}, kb={}）",
                document_id, document.enable_llm_clean, kb.enable_llm_clean,
            )
            DocumentService.update_status(db, document_id, DocumentStatus.CLEANING)
            try:
                from app.rag.cleaner import clean_document_with_llm
                text_before = len(text)
                text = clean_document_with_llm(text)
                logger.info(
                    "[Task] LLM 清洗完成 document_id={} {}→{} 字符",
                    document_id, text_before, len(text),
                )
            except Exception as e:
                # 整体清洗失败时降级到启发式版（不阻断主管道）
                logger.warning(
                    "[Task] LLM 清洗整体失败 document_id={}，沿用启发式解析结果: {}",
                    document_id, e,
                )
        TaskService.update_progress(db, task_record_id, progress=30)

        # ---------- 阶段 3：分块 ----------
        DocumentService.update_status(db, document_id, DocumentStatus.CHUNKING)
        # 文档级策略优先；为空则回退 KB 默认。size/overlap 始终用 KB 配置。
        effective_strategy = document.chunk_strategy or kb.chunk_strategy
        logger.info(
            "[Task] 分块策略选择 document_id={}: doc.chunk_strategy={}, kb.chunk_strategy={}, 实际使用={}",
            document_id,
            document.chunk_strategy.value if document.chunk_strategy else None,
            kb.chunk_strategy.value,
            effective_strategy.value,
        )
        splitter = get_splitter(
            strategy=effective_strategy,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
        )
        chunks = splitter.split(text)
        if not chunks:
            raise ValueError("文档分块结果为空")

        TaskService.update_progress(db, task_record_id, progress=50)

        # ---------- 阶段 4：向量化 ----------
        DocumentService.update_status(db, document_id, DocumentStatus.EMBEDDING)
        embedder = get_embedder()
        contents: List[str] = [c.content for c in chunks]

        # 向量化时拼接 header_path 作为语义增强
        # 让 embedding 能更好地捕捉 chunk 所属的章节主题
        embed_texts: List[str] = []
        for c in chunks:
            header = c.metadata.get("header_path", "")
            if header and header != "(no-header)":
                embed_texts.append(f"[{header}] {c.content}")
            else:
                embed_texts.append(c.content)
        embeddings = embedder.embed_texts(embed_texts)

        TaskService.update_progress(db, task_record_id, progress=85)

        # ---------- 阶段 5：写入向量库 ----------
        chunk_ids = [f"doc_{document.id}_chunk_{i}" for i in range(len(chunks))]
        # 把 document/file_name 元数据也存进去，便于检索后回溯来源
        metadatas = [
            {
                **c.metadata,
                "document_id": document.id,
                "kb_id": kb.id,
                "file_name": document.file_name,
            }
            for c in chunks
        ]

        vector_store = get_vector_store()
        DocumentService.update_status(db, document_id, DocumentStatus.STORING)
        vector_store.add_chunks(
            collection_name=kb.collection_name,
            chunk_ids=chunk_ids,
            documents=contents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # ---------- 阶段 6：完成 ----------
        DocumentService.update_status(
            db, document_id, DocumentStatus.COMPLETED, chunk_count=len(chunks),
        )
        TaskService.update_progress(
            db, task_record_id, progress=100, status=TaskStatus.SUCCESS,
        )

        elapsed = time.time() - start_ts
        logger.info(
            "[Task] 文档处理完成 document_id={} chunks={} embedder={} 耗时={:.2f}s",
            document_id, len(chunks), type(embedder).__name__, elapsed,
        )
        return {
            "document_id": document_id,
            "chunk_count": len(chunks),
            "elapsed_seconds": round(elapsed, 2),
        }

    except Exception as e:
        logger.exception("[Task] 文档处理失败 document_id={}: {}", document_id, e)
        # 标记失败
        DocumentService.update_status(
            db, document_id, DocumentStatus.FAILED, error_msg=str(e),
        )
        TaskService.update_progress(
            db, task_record_id, status=TaskStatus.FAILED, error_msg=str(e),
        )
        # 不重新抛出（避免 Celery 把任务标记为 RETRY/FAILURE 而重复执行），
        # 但仍然返回错误信息供查询
        return {
            "document_id": document_id,
            "error": str(e),
        }
    finally:
        db.close()
