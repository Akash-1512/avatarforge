"""Add full script (narration) column to video_jobs — the library shows it.

Revision ID: 0004_add_script
Revises: 0003_add_language
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_add_script"
down_revision = "0003_add_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_jobs", sa.Column("script", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("video_jobs", "script")
