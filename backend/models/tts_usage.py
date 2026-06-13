"""TTS usage audit table — one row per synthesis call."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.db import Base


class TTSUsage(Base):
    __tablename__ = "tts_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    job_id: Mapped[str] = mapped_column(String(32), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    model: Mapped[str] = mapped_column(String(100))
    voice_preset: Mapped[str] = mapped_column(String(50))
    characters: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    audio_duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_type: Mapped[str] = mapped_column(String(100), nullable=True)
