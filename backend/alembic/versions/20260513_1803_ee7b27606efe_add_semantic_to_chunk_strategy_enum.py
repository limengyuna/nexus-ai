"""add semantic to chunk strategy enum

Revision ID: ee7b27606efe
Revises: 9b5e75d9db39
Create Date: 2026-05-13 18:03:00.676883+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee7b27606efe'
down_revision: Union[str, None] = '9b5e75d9db39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 给 ENUM 增加新枚举值的官方方式
    # 必须在事务外执行（Alembic 默认在事务内，所以加 COMMIT 或用 connection.execute）
    # 用 IF NOT EXISTS 保证幂等
    # 注意：初始迁移中 enum 值使用大写名称（RECURSIVE / MARKDOWN_HEADER），这里保持一致
    op.execute("ALTER TYPE chunk_strategy_enum ADD VALUE IF NOT EXISTS 'SEMANTIC'")


def downgrade() -> None:
    # 注：PostgreSQL 无法直接从 ENUM 移除单个值
    # 真正回退需要：1)新建 ENUM 不含该值 2)迁移数据 3)切换列类型 4)删旧 ENUM
    # 为简化，downgrade 留空（前向兼容场景下足够）
    pass
