"""
知识库模型
"""
import enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class ChunkStrategy(str, enum.Enum):
    """文档分块策略枚举"""
    RECURSIVE = "recursive"          # 通用递归字符分块（默认）
    MARKDOWN_HEADER = "markdown"     # Markdown 按标题分块
    SEMANTIC = "semantic"            # 基于 Embedding 语义跳变的智能切分


class KnowledgeBase(Base, TimestampMixin):
    """知识库表"""

    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="知识库名称",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="知识库描述",
    )

    # ---------- 分块策略配置 ----------
    chunk_strategy: Mapped[ChunkStrategy] = mapped_column(
        SAEnum(ChunkStrategy, name="chunk_strategy_enum"),
        default=ChunkStrategy.RECURSIVE,
        nullable=False,
        comment="分块策略",
    )

    chunk_size: Mapped[int] = mapped_column(
        Integer,
        default=500,
        nullable=False,
        comment="分块大小（字符数）",
    )

    chunk_overlap: Mapped[int] = mapped_column(
        Integer,
        default=50,
        nullable=False,
        comment="分块重叠（字符数）",
    )

    # ---------- LLM 文档清洗开关 ----------
    # 启用后，文档解析阶段会额外调用 LLM 把"伪 Markdown"重排为结构清晰的标准 Markdown，
    # 适合扫描版 / 格式混乱的中文 PDF；对结构已清晰的文档帮助不大且增加 token 成本。
    enable_llm_clean: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="是否启用 LLM 文档清洗（可选预处理层）",
    )

    # ---------- 向量集合标识 ----------
    # 对应 ChromaDB 中的 collection 名称，通常用 "kb_{id}" 命名
    collection_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        comment="向量库 Collection 名称",
    )

    # ---------- 关联关系 ----------
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="创建人 ID",
    )

    creator: Mapped["User"] = relationship(
        back_populates="knowledge_bases",
        foreign_keys=[created_by],
    )

    documents: Mapped[List["Document"]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeBase id={self.id} name={self.name!r}>"
