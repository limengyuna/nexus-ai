"""add cleaning and storing to document_status

Revision ID: 316a2418558e
Revises: 8a4c1d2e3f60
Create Date: 2026-06-15 18:35:58.114331+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '316a2418558e'
down_revision: Union[str, None] = '8a4c1d2e3f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'cleaning'")
        op.execute("ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'storing'")


def downgrade() -> None:
    # PostgreSQL does not support dropping enum values easily.
    pass
