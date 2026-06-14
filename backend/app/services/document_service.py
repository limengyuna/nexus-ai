"""
文档业务逻辑层

职责：
1. 接收上传文件并保存到磁盘
2. 在数据库中登记 Document 记录
3. 创建 TaskRecord 并投递 Celery 异步处理任务
4. 删除时同步清理向量库 + 物理文件
"""
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.knowledge_base import ChunkStrategy, KnowledgeBase
from app.models.task import TaskRecord, TaskStatus, TaskType
from app.rag.parser import DocumentParser
from app.rag.vector_store import get_vector_store


class DocumentService:
    """文档相关业务方法集合"""

    # ---------- 内部工具 ----------
    @staticmethod
    def _resolve_upload_dir(kb_id: int) -> Path:
        """每个知识库一个独立子目录，避免文件名冲突"""
        upload_dir = Path(settings.UPLOAD_DIR) / f"kb_{kb_id}"
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    # ---------- 上传 + 提交异步任务 ----------
    @staticmethod
    def upload(
        db: Session,
        kb: KnowledgeBase,
        upload_file: UploadFile,
        user_id: int,
        chunk_strategy: Optional[ChunkStrategy] = None,
        enable_llm_clean: Optional[bool] = None,
    ) -> tuple[Document, TaskRecord]:
        """
        上传文件，登记 Document + 创建 TaskRecord，并触发 Celery 任务

        :param chunk_strategy: 文档级分块策略；不传则沿用 KB 默认
        :param enable_llm_clean: 文档级 LLM 清洗开关；不传则沿用 KB 默认
        :return: (Document, TaskRecord)
        :raises ValueError: 文件类型不支持 / 文件超限
        """
        original_name = upload_file.filename or "unnamed"

        # 1. 校验文件类型
        if not DocumentParser.is_supported(original_name):
            raise ValueError(
                f"不支持的文件类型，仅支持: {', '.join(DocumentParser.supported_extensions())}"
            )

        # 2. 保存到磁盘（用 UUID 防止文件名冲突 / 越权访问）
        ext = Path(original_name).suffix.lower()
        safe_name = f"{uuid.uuid4().hex}{ext}"
        upload_dir = DocumentService._resolve_upload_dir(kb.id)
        save_path = upload_dir / safe_name

        # 流式写入，避免大文件占用内存；同时统计大小
        file_size = 0
        with save_path.open("wb") as f:
            while chunk := upload_file.file.read(1024 * 1024):  # 1MB
                file_size += len(chunk)
                if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                    f.close()
                    save_path.unlink(missing_ok=True)
                    raise ValueError(
                        f"文件超过最大限制 {settings.MAX_UPLOAD_SIZE_MB} MB"
                    )
                f.write(chunk)

        logger.info("文件已保存: {} -> {} ({} bytes)", original_name, save_path, file_size)

        # 3. 登记 Document 记录
        document = Document(
            kb_id=kb.id,
            file_name=original_name,
            file_type=ext.lstrip("."),
            file_size=file_size,
            file_path=str(save_path),
            status=DocumentStatus.PENDING,
            chunk_strategy=chunk_strategy,        # 可为 None：处理时回退 KB 默认
            enable_llm_clean=enable_llm_clean,    # 可为 None：处理时回退 KB 默认
        )
        db.add(document)
        db.flush()

        # 4. 创建 TaskRecord
        task_record = TaskRecord(
            user_id=user_id,
            type=TaskType.DOCUMENT_PROCESS,
            status=TaskStatus.PENDING,
            related_id=document.id,
            progress=0,
        )
        db.add(task_record)
        db.commit()
        db.refresh(document)
        db.refresh(task_record)

        # 5. 投递 Celery 任务（异步执行）
        # 延迟导入，避免循环依赖（celery_app 也间接 import config）
        from app.tasks.document_tasks import process_document

        async_result = process_document.delay(document.id, task_record.id)
        task_record.celery_task_id = async_result.id
        db.commit()
        db.refresh(task_record)

        logger.info(
            "文档处理任务已投递: document_id={}, task_record_id={}, celery_id={}",
            document.id, task_record.id, async_result.id,
        )
        return document, task_record

    # ---------- 查询 ----------
    @staticmethod
    def get(db: Session, document_id: int) -> Optional[Document]:
        return db.get(Document, document_id)

    @staticmethod
    def list_by_kb(db: Session, kb_id: int) -> List[Document]:
        return (
            db.query(Document)
            .filter(Document.kb_id == kb_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    # ---------- 删除 ----------
    @staticmethod
    def delete(db: Session, document: Document) -> None:
        """删除文档：清理向量库分块 + 物理文件 + 数据库记录"""
        kb = db.get(KnowledgeBase, document.kb_id)
        # 1. 清理向量库中该文档的所有分块
        if kb and kb.collection_name:
            try:
                get_vector_store().delete_by_metadata(
                    collection_name=kb.collection_name,
                    where={"document_id": document.id},
                )
            except Exception as e:
                logger.warning("删除向量库分块失败: {}", e)

        # 2. 清理物理文件
        try:
            Path(document.file_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("删除物理文件失败: {}", e)

        # 3. 删除数据库记录
        db.delete(document)
        db.commit()

    # ---------- 重新处理 ----------
    @staticmethod
    def reprocess(db: Session, document: Document, user_id: int) -> TaskRecord:
        """
        重新处理文档：清理旧分块 + 重置状态 + 重新投递 Celery 任务
        适用于：上次处理失败、或修改了 KB 的分块策略后想重切

        :return: 新创建的 TaskRecord
        """
        kb = db.get(KnowledgeBase, document.kb_id)

        # 1. 清理旧向量库分块
        if kb and kb.collection_name:
            try:
                get_vector_store().delete_by_metadata(
                    collection_name=kb.collection_name,
                    where={"document_id": document.id},
                )
            except Exception as e:
                logger.warning("[reprocess] 清理旧向量失败: {}", e)

        # 2. 重置文档状态
        document.status = DocumentStatus.PENDING
        document.chunk_count = 0
        document.error_msg = None

        # 3. 创建新 TaskRecord
        task_record = TaskRecord(
            user_id=user_id,
            type=TaskType.DOCUMENT_PROCESS,
            status=TaskStatus.PENDING,
            related_id=document.id,
            progress=0,
        )
        db.add(task_record)
        db.commit()
        db.refresh(document)
        db.refresh(task_record)

        # 4. 投递 Celery 任务
        from app.tasks.document_tasks import process_document

        async_result = process_document.delay(document.id, task_record.id)
        task_record.celery_task_id = async_result.id
        db.commit()
        db.refresh(task_record)

        logger.info(
            "[reprocess] 文档已重新投递: document_id={}, new_task_id={}",
            document.id, task_record.id,
        )
        return task_record

    # ---------- 状态机更新（供 Celery 任务调用） ----------
    @staticmethod
    def update_status(
        db: Session,
        document_id: int,
        status: DocumentStatus,
        chunk_count: Optional[int] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        """更新文档处理状态（独立函数便于 Celery 任务调用）"""
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = status
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        if error_msg is not None:
            doc.error_msg = error_msg
        db.commit()


class TaskService:
    """任务记录查询与更新"""

    @staticmethod
    def get(db: Session, task_id: int) -> Optional[TaskRecord]:
        return db.get(TaskRecord, task_id)

    @staticmethod
    def get_for_user(
        db: Session,
        task_id: int,
        user_id: int,
    ) -> Optional[TaskRecord]:
        return (
            db.query(TaskRecord)
            .filter(
                TaskRecord.id == task_id,
                TaskRecord.user_id == user_id,
            )
            .first()
        )

    @staticmethod
    def update_progress(
        db: Session,
        task_id: int,
        progress: Optional[int] = None,
        status: Optional[TaskStatus] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        """供 Celery 任务调用，更新进度/状态"""
        task = db.get(TaskRecord, task_id)
        if task is None:
            return
        if progress is not None:
            task.progress = max(0, min(100, progress))
        if status is not None:
            task.status = status
            if status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.finished_at = datetime.now(timezone.utc)
        if error_msg is not None:
            task.error_msg = error_msg
        db.commit()
