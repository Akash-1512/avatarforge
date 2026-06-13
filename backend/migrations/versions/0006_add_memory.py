"""Add chat history, long-term memory, and user preference tables.

Revision ID: 0006_add_memory
Revises: 0005_add_trace_job_id
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_add_memory"
down_revision = "0005_add_trace_job_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("thread_id", sa.String(64)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("role", sa.String(16)),
        sa.Column("content", sa.Text),
    )
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])

    op.create_table(
        "user_memories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("kind", sa.String(32)),
        sa.Column("value", sa.String(255)),
        sa.Column("source", sa.String(255)),
        sa.Column("active", sa.Boolean),
    )
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])
    op.create_index("ix_user_memories_active", "user_memories", ["active"])
    op.create_index("ix_user_memories_created_at", "user_memories", ["created_at"])

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("memory_enabled", sa.Boolean),
        sa.Column("default_tone", sa.String(20), nullable=True),
        sa.Column("default_language", sa.String(5), nullable=True),
        sa.Column("default_duration", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_table("user_memories")
    op.drop_table("chat_messages")
