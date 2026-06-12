"""Video generation job — the persistent record every pipeline run writes to.

Status lifecycle: queued -> running -> completed | failed.
Failed jobs additionally land in the Redis dead-letter queue for inspection.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    current_stage: Mapped[str] = mapped_column(String(20), nullable=True)
    celery_task_id: Mapped[str] = mapped_column(String(64), nullable=True)

    # Inputs
    topic: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(String(20), default="professional")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=60)
    voice: Mapped[str] = mapped_column(String(40), default="professional_female")
    image_file_id: Mapped[str] = mapped_column(String(64))
    preprocess: Mapped[str] = mapped_column(String(20), default="crop")
    engine: Mapped[str] = mapped_column(String(20), default="sadtalker")

    # Outputs
    script_title: Mapped[str] = mapped_column(Text, nullable=True)
    audio_file_id: Mapped[str] = mapped_column(String(64), nullable=True)
    video_file_id: Mapped[str] = mapped_column(String(64), nullable=True)
    video_url: Mapped[str] = mapped_column(String(200), nullable=True)
    stage_timings: Mapped[dict] = mapped_column(JSON, default=dict)

    # Failure info
    error_type: Mapped[str] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
