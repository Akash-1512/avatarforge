"""Add job_id correlation column to the audit tables (per-job tracing).

Revision ID: 0005_add_trace_job_id
Revises: 0004_add_script
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_add_trace_job_id"
down_revision = "0004_add_script"
branch_labels = None
depends_on = None

_TABLES = ("token_usage", "tts_usage", "avatar_usage")


def upgrade() -> None:
    for t in _TABLES:
        op.add_column(t, sa.Column("job_id", sa.String(32), nullable=True))
        op.create_index(f"ix_{t}_job_id", t, ["job_id"])


def downgrade() -> None:
    for t in _TABLES:
        op.drop_index(f"ix_{t}_job_id", t)
        op.drop_column(t, "job_id")
