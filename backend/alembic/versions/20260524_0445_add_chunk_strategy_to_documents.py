"""add chunk_strategy to documents

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-05-24 04:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents 表新增 chunk_strategy 字段（可空，复用现有 chunk_strategy_enum）
    # 已有文档保持 NULL，处理时回退到 KB 默认策略
    op.add_column(
        "documents",
        sa.Column(
            "chunk_strategy",
            postgresql.ENUM(
                "recursive",
                "markdown",
                "semantic",
                name="chunk_strategy_enum",
                create_type=False,
            ),
            nullable=True,
            comment="文档级分块策略（null 表示使用 KB 默认）",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "chunk_strategy")
