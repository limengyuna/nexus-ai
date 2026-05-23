"""add enable_llm_clean to documents

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-05-24 04:50:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents 表新增 enable_llm_clean 字段（可空）
    # null 表示沿用 KB 默认；显式 true/false 用于上传时覆盖
    op.add_column(
        "documents",
        sa.Column(
            "enable_llm_clean",
            sa.Boolean(),
            nullable=True,
            comment="文档级 LLM 清洗开关（null 表示使用 KB 默认）",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "enable_llm_clean")
