"""add cached_tools and tool_count to mcp_server_configs

Revision ID: a1b2c3d4e5f6
Revises: 500d84ac8fa8
Create Date: 2026-05-21 14:25:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "a1b2c3d4e5f6"
down_revision = "500d84ac8fa8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_server_configs",
        sa.Column("cached_tools", sa.JSON(), nullable=True, comment="缓存的子工具清单（JSON Array）"),
    )
    op.add_column(
        "mcp_server_configs",
        sa.Column("tool_count", sa.Integer(), nullable=False, server_default="0", comment="子工具数量"),
    )


def downgrade() -> None:
    op.drop_column("mcp_server_configs", "tool_count")
    op.drop_column("mcp_server_configs", "cached_tools")
