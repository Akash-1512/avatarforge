"""Long-term memory and explicit preferences — the cross-session layer.

Two tables, mirroring how a transparent memory product (e.g. Claude's memory +
preference settings) separates the two kinds of long-term state:

- UserMemory: facts the agent *learned* from conversations ("prefers Hindi",
  "usually wants 30s"). Auto-extracted, but user-visible and individually
  deletable. Each carries its source so the user can see why it's remembered.
- UserPreference: settings the user *chose* explicitly (default tone, language,
  duration) plus the master memory_enabled switch. Chosen settings always win
  over learned memories.

Both are keyed by user_id. Auth doesn't exist yet, so user_id is supplied by the
client; real identity slots in here unchanged.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.db import Base


class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # tone | language | duration | note
    value: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(255), default="")  # why it was remembered
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    default_tone: Mapped[str] = mapped_column(String(20), nullable=True)
    default_language: Mapped[str] = mapped_column(String(5), nullable=True)
    default_duration: Mapped[int] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
