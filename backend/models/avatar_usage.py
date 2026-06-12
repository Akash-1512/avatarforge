"""Avatar generation audit table — one row per inference attempt."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.db import Base


class AvatarUsage(Base):
    __tablename__ = "avatar_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    audio_file_id: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(20), default="sadtalker")
    preprocess: Mapped[str] = mapped_column(String(20), default="crop")
    enhancer: Mapped[bool] = mapped_column(Boolean, default=False)
    video_duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_type: Mapped[str] = mapped_column(String(100), nullable=True)
