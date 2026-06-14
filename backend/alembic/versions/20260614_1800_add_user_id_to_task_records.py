"""Add task ownership to task_records.

Revision ID: 8a4c1d2e3f60
Revises: 797fd0d5e59a
Create Date: 2026-06-14 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a4c1d2e3f60"
down_revision: Union[str, None] = "797fd0d5e59a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_records",
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True,
            comment="Task owner user ID",
        ),
    )

    # Existing document tasks inherit ownership from their knowledge base.
    op.execute(
        """
        UPDATE task_records AS task
        SET user_id = kb.created_by
        FROM documents AS doc
        JOIN knowledge_bases AS kb ON kb.id = doc.kb_id
        WHERE task.related_id = doc.id
          AND task.type = 'DOCUMENT_PROCESS'
          AND task.user_id IS NULL
        """
    )

    # Finished tasks whose documents were already deleted no longer have a
    # trustworthy owner relation. They are stale operational metadata and can
    # be removed instead of being assigned to an unrelated user.
    op.execute(
        """
        DELETE FROM task_records AS task
        WHERE task.user_id IS NULL
          AND task.type = 'DOCUMENT_PROCESS'
          AND task.status IN ('SUCCESS', 'FAILED', 'CANCELLED')
          AND NOT EXISTS (
              SELECT 1
              FROM documents AS doc
              WHERE doc.id = task.related_id
          )
        """
    )

    # Do not silently assign any remaining orphaned task to an unrelated user.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM task_records
                WHERE user_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot backfill task_records.user_id: orphan task records exist';
            END IF;
        END
        $$;
        """
    )

    op.alter_column(
        "task_records",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_task_records_user_id_users",
        "task_records",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_task_records_user_id"),
        "task_records",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_records_user_id"), table_name="task_records")
    op.drop_constraint(
        "fk_task_records_user_id_users",
        "task_records",
        type_="foreignkey",
    )
    op.drop_column("task_records", "user_id")
