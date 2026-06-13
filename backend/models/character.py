"""Character — a reusable digital character asset.

Created once from an uploaded photo, a video, or a live capture, then reused
across many scenes and films. Stores the reference frames extracted at ingest
(the identity signal handed to reference-capable scene engines), the chosen
default style, and an optional cloned-voice id. A character is engine-agnostic:
the scene-engine registry decides at render time which engine can serve a given
style and content policy (e.g. a real-person reference goes to a reference-capable
engine, never to one that rejects human faces).
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.db import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # how the source was provided: "photo" | "video" | "live"
    source_kind: Mapped[str] = mapped_column(String(16), default="photo")
    # comma-separated storage file ids of the extracted reference frames
    reference_frame_ids: Mapped[str] = mapped_column(Text, default="")
    # default render style: "realistic" | "anime" | "pixar" | ...
    default_style: Mapped[str] = mapped_column(String(32), default="realistic")
    # whether the reference contains a real human face — decides engine routing,
    # since some engines (Azure Sora 2) reject real human faces by policy
    is_real_person: Mapped[bool] = mapped_column(default=True)
    # optional cloned-voice id (e.g. an ElevenLabs voice), set in a later phase
    voice_id: Mapped[str] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ready")  # ready | failed
    frame_count: Mapped[int] = mapped_column(Integer, default=0)

    def frame_ids(self) -> list[str]:
        return [f for f in (self.reference_frame_ids or "").split(",") if f]
