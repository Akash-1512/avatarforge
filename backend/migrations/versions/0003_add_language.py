"""Add language column to video_jobs (multi-language synthesis).

Revision ID: 0003_add_language
Revises: 0002_add_engine
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_add_language"
down_revision = "0002_add_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "video_jobs",
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("video_jobs", "language")
