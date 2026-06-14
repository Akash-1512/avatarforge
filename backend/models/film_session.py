"""FilmSession — a persistent, conversational film a user builds and refines.

Unlike the one-shot cast-compose, a session is durable and iterative: it holds the
*interpretation* (how the app understood the request, shown to the user before
rendering), the storyboard, the rendered scene clips, and the full conversation
history. Follow-up messages ("make scene 2 brighter", "swap KAI's voice") act on
this same session, so the film evolves through chat rather than starting over.

State is stored as JSON blobs (interpretation, cast, storyboard, scenes) so the shape
can evolve without a migration per field; the columns that are queried (owner, status,
updated_at) are real columns.
"""

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.db import Base


class FilmSession(Base):
    __tablename__ = "film_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    # lifecycle: created -> interpreting -> ready_to_render -> rendering -> done | failed
    status: Mapped[str] = mapped_column(String(24), default="created")
    theme: Mapped[str] = mapped_column(String(40), default="")
    script: Mapped[str] = mapped_column(Text, default="")
    clip_id: Mapped[str] = mapped_column(String(80), default="")  # latest rendered film

    # JSON blobs
    cast_json: Mapped[str] = mapped_column(Text, default="[]")
    interpretation_json: Mapped[str] = mapped_column(Text, default="{}")
    storyboard_json: Mapped[str] = mapped_column(Text, default="{}")
    scenes_json: Mapped[str] = mapped_column(Text, default="[]")
    history_json: Mapped[str] = mapped_column(Text, default="[]")

    # typed accessors -------------------------------------------------------
    _LIST_FIELDS = {"cast_json", "scenes_json", "history_json"}

    def _get(self, field: str) -> Any:
        default = "[]" if field in self._LIST_FIELDS else "{}"
        return json.loads(getattr(self, field) or default)

    def _set(self, field: str, value: Any) -> None:
        setattr(self, field, json.dumps(value))

    @property
    def cast(self) -> list:
        return self._get("cast_json")

    @property
    def interpretation(self) -> dict:
        return self._get("interpretation_json")

    @property
    def storyboard(self) -> dict:
        return self._get("storyboard_json")

    @property
    def scenes(self) -> list:
        return self._get("scenes_json")

    @property
    def history(self) -> list:
        return self._get("history_json")

    def append_history(self, role: str, content: str) -> None:
        h = self.history
        h.append({"role": role, "content": content, "at": datetime.now(timezone.utc).isoformat()})
        self._set("history_json", h)

    def payload(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "theme": self.theme,
            "clip_id": self.clip_id or None,
            "cast": self.cast,
            "interpretation": self.interpretation,
            "scene_count": len(self.scenes),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
