"""
文档模型
"""
import enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.knowledge_base import ChunkStrategy

if TYPE_CHECKING:
    from app.models.knowledge_base import KnowledgeBase


class DocumentStatus(str, enum.Enum):
    """文档处理状态枚举"""
    PENDING = "pending"        # 等待处理
    PARSING = "parsing"        # 解析中
    CLEANING = "cleaning"      # LLM 清洗中
    CHUNKING = "chunking"      # 分块中
    EMBEDDING = "embedding"    # 向量化中
    STORING = "storing"        # 入库中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败


class Document(Base, TimestampMixin):
    """文档表"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="原始文件名",
    )

    file_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="文件类型（pdf/docx/md/txt 等）",
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="文件大小（字节）",
    )

    file_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="服务器存储路径",
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="分块数量（处理完成后填充）",
    )

    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status_enum"),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
        comment="文档处理状态",
    )

    # 文档级分块策略（可空：null 表示沿用所属知识库的默认策略）
    # 允许同一 KB 内不同文档使用不同切分策略（如论文用 markdown，对话用 semantic）
    chunk_strategy: Mapped[Optional[ChunkStrategy]] = mapped_column(
        SAEnum(ChunkStrategy, name="chunk_strategy_enum", create_type=False),
        nullable=True,
        comment="文档级分块策略（null 表示使用 KB 默认）",
    )

    # 文档级 LLM 清洗开关（可空：null 表示沿用所属知识库的默认设置）
    # 允许某些文档单独启用/禁用 LLM 清洗，而不影响 KB 里其他文档
    enable_llm_clean: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="文档级 LLM 清洗开关（null 表示使用 KB 默认）",
    )

    error_msg: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="失败时的错误信息",
    )

    # ---------- 关联关系 ----------
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属知识库 ID",
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        back_populates="documents",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} file_name={self.file_name!r} status={self.status.value}>"
