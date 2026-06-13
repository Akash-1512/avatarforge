"""Add the characters table (reusable digital character assets).

Revision ID: 0007_add_characters
Revises: 0006_add_memory
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_add_characters"
down_revision = "0006_add_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("name", sa.String(120)),
        sa.Column("source_kind", sa.String(16)),
        sa.Column("reference_frame_ids", sa.Text),
        sa.Column("default_style", sa.String(32)),
        sa.Column("is_real_person", sa.Boolean),
        sa.Column("voice_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16)),
        sa.Column("frame_count", sa.Integer),
    )
    op.create_index("ix_characters_user_id", "characters", ["user_id"])
    op.create_index("ix_characters_created_at", "characters", ["created_at"])


def downgrade() -> None:
    op.drop_table("characters")
