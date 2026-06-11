"""initial tables: token_usage, tts_usage, avatar_usage, video_jobs

Revision ID: 0001
Revises:
Create Date: 2026-06-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True),
        sa.Column("provider", sa.String(50), index=True),
        sa.Column("model", sa.String(100)),
        sa.Column("operation", sa.String(50)),
        sa.Column("prompt_tokens", sa.Integer),
        sa.Column("completion_tokens", sa.Integer),
        sa.Column("total_tokens", sa.Integer),
        sa.Column("estimated_cost_usd", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("success", sa.Boolean),
        sa.Column("error_type", sa.String(100), nullable=True),
    )
    op.create_table(
        "tts_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True),
        sa.Column("provider", sa.String(50), index=True),
        sa.Column("model", sa.String(100)),
        sa.Column("voice_preset", sa.String(50)),
        sa.Column("characters", sa.Integer),
        sa.Column("estimated_cost_usd", sa.Float),
        sa.Column("audio_duration_sec", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("success", sa.Boolean),
        sa.Column("error_type", sa.String(100), nullable=True),
    )
    op.create_table(
        "avatar_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True),
        sa.Column("audio_file_id", sa.String(64)),
        sa.Column("preprocess", sa.String(20)),
        sa.Column("enhancer", sa.Boolean),
        sa.Column("video_duration_sec", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("success", sa.Boolean),
        sa.Column("error_type", sa.String(100), nullable=True),
    )
    op.create_table(
        "video_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), index=True),
        sa.Column("current_stage", sa.String(20), nullable=True),
        sa.Column("celery_task_id", sa.String(64), nullable=True),
        sa.Column("topic", sa.Text),
        sa.Column("tone", sa.String(20)),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("voice", sa.String(40)),
        sa.Column("image_file_id", sa.String(64)),
        sa.Column("preprocess", sa.String(20)),
        sa.Column("script_title", sa.Text, nullable=True),
        sa.Column("audio_file_id", sa.String(64), nullable=True),
        sa.Column("video_file_id", sa.String(64), nullable=True),
        sa.Column("video_url", sa.String(200), nullable=True),
        sa.Column("stage_timings", sa.JSON),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("video_jobs")
    op.drop_table("avatar_usage")
    op.drop_table("tts_usage")
    op.drop_table("token_usage")
