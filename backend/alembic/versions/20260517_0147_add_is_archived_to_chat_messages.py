"""add is_archived to chat_messages

Revision ID: a3f1c2d4e5b6
Revises: ee7b27606efe
Create Date: 2026-05-17 01:47:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c2d4e5b6'
down_revision: Union[str, None] = 'ee7b27606efe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chat_messages',
        sa.Column(
            'is_archived',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='是否已被摘要压缩归档',
        ),
    )


def downgrade() -> None:
    op.drop_column('chat_messages', 'is_archived')
