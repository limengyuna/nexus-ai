"""add enable_llm_clean to knowledge_bases

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-24 03:25:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "c7d8e9f0a1b2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 给 knowledge_bases 表增加 enable_llm_clean 开关字段
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "enable_llm_clean",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="是否启用 LLM 文档清洗（可选预处理层）",
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "enable_llm_clean")
