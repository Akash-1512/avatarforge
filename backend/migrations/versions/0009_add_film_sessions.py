"""Add film_sessions (persistent conversational films).

Revision ID: 0009_add_film_sessions
Revises: 0008_add_users
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_add_film_sessions"
down_revision = "0008_add_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "film_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("title", sa.String(200)),
        sa.Column("status", sa.String(24)),
        sa.Column("theme", sa.String(40)),
        sa.Column("script", sa.Text),
        sa.Column("clip_id", sa.String(80)),
        sa.Column("cast_json", sa.Text),
        sa.Column("interpretation_json", sa.Text),
        sa.Column("storyboard_json", sa.Text),
        sa.Column("scenes_json", sa.Text),
        sa.Column("history_json", sa.Text),
    )
    op.create_index("ix_film_sessions_user_id", "film_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("film_sessions")
