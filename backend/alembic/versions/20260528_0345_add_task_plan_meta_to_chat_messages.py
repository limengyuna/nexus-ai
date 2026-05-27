"""add task_plan_meta to chat_messages

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-05-28 03:45:00.000000

用户取消当前轮次时把 task_plan 持久化到此字段（仅 assistant 消息使用），
下一轮 supervisor 规划阶段读取它，让 LLM 跳过已完成的 step、重跑被中断的 step。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chat_messages 表新增 task_plan_meta JSONB 列
    op.add_column(
        "chat_messages",
        sa.Column(
            "task_plan_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="任务计划元信息：上一轮 task_plan 状态 + 是否被中断（用于跨轮续跑）",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "task_plan_meta")
