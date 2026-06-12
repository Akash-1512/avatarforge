"""Add engine column to video_jobs and avatar_usage (multi-engine routing).

Revision ID: 0002_add_engine
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_add_engine"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "video_jobs",
        sa.Column("engine", sa.String(20), nullable=False, server_default="sadtalker"),
    )
    op.add_column(
        "avatar_usage",
        sa.Column("engine", sa.String(20), nullable=False, server_default="sadtalker"),
    )


def downgrade() -> None:
    op.drop_column("avatar_usage", "engine")
    op.drop_column("video_jobs", "engine")
