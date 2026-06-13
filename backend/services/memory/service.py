"""Memory service — short-term thread, long-term memory, explicit preferences.

The conversational layer's memory, modelled on a transparent, user-controlled
memory product:

- Short-term: a chat thread (list of messages) keyed by thread_id. This is the
  rolling context the planner refines against, and the chat history in the UI.
- Long-term: per-user learned memories (auto-extracted preferences with a
  visible source) and explicitly chosen preferences. Chosen settings win over
  learned ones; both feed the planner as defaults on a new conversation.
- Control: a memory_enabled switch. When off, nothing is learned or recalled —
  threads still work, but the long-term layer is inert. Users can view every
  memory and delete them individually or all at once.

Everything runs on the existing async SQLAlchemy stack; the session factory is
resolved lazily so it honours the per-task engine reset in the worker.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import delete, select, update

from backend.models.chat import ChatMessage
from backend.models.memory import UserMemory, UserPreference
from backend.observability.logging import get_logger

logger = get_logger(__name__)

_VALID_TONES = {"professional", "casual", "enthusiastic", "formal", "friendly"}


@dataclass
class Preferences:
    memory_enabled: bool = True
    default_tone: Optional[str] = None
    default_language: Optional[str] = None
    default_duration: Optional[int] = None


@dataclass
class MemoryView:
    """What the UI shows under 'memory & preferences'."""

    preferences: Preferences
    memories: List[dict] = field(default_factory=list)


class MemoryService:
    def __init__(self, session_factory=None):
        self._injected = session_factory

    @property
    def _sf(self):
        if self._injected is not None:
            return self._injected
        from backend.models.db import get_session_factory

        return get_session_factory()

    # ---- short-term: conversation thread ----
    async def load_thread(self, thread_id: str, limit: int = 40) -> List[dict]:
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(ChatMessage)
                        .where(ChatMessage.thread_id == thread_id)
                        .order_by(ChatMessage.id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [{"role": r.role, "content": r.content} for r in rows]

    async def append_message(self, thread_id: str, user_id: str, role: str, content: str) -> None:
        async with self._sf() as s:
            s.add(ChatMessage(thread_id=thread_id, user_id=user_id, role=role, content=content))
            await s.commit()

    # ---- explicit preferences (chosen) ----
    async def get_preferences(self, user_id: str) -> Preferences:
        async with self._sf() as s:
            row = await s.get(UserPreference, user_id)
            if row is None:
                return Preferences()
            return Preferences(
                memory_enabled=row.memory_enabled,
                default_tone=row.default_tone,
                default_language=row.default_language,
                default_duration=row.default_duration,
            )

    async def set_preferences(self, user_id: str, **fields) -> Preferences:
        # only persist known, validated fields
        clean = {}
        if "memory_enabled" in fields and fields["memory_enabled"] is not None:
            clean["memory_enabled"] = bool(fields["memory_enabled"])
        if fields.get("default_tone") in _VALID_TONES:
            clean["default_tone"] = fields["default_tone"]
        if fields.get("default_language"):
            clean["default_language"] = str(fields["default_language"])[:5]
        if fields.get("default_duration") is not None:
            d = int(fields["default_duration"])
            if 15 <= d <= 300:
                clean["default_duration"] = d
        async with self._sf() as s:
            row = await s.get(UserPreference, user_id)
            if row is None:
                row = UserPreference(user_id=user_id, memory_enabled=True)
                s.add(row)
            for k, v in clean.items():
                setattr(row, k, v)
            await s.commit()
        return await self.get_preferences(user_id)

    # ---- long-term: learned memories ----
    async def recall(self, user_id: str) -> List[dict]:
        prefs = await self.get_preferences(user_id)
        if not prefs.memory_enabled:
            return []
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(UserMemory)
                        .where(UserMemory.user_id == user_id, UserMemory.active.is_(True))
                        .order_by(UserMemory.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [
                {"id": r.id, "kind": r.kind, "value": r.value, "source": r.source} for r in rows
            ]

    async def remember(self, user_id: str, kind: str, value: str, source: str = "") -> None:
        """Upsert a learned memory of a given kind (one active value per kind)."""
        prefs = await self.get_preferences(user_id)
        if not prefs.memory_enabled:
            return
        async with self._sf() as s:
            # deactivate any prior memory of the same kind, then insert the new one
            await s.execute(
                update(UserMemory)
                .where(
                    UserMemory.user_id == user_id,
                    UserMemory.kind == kind,
                    UserMemory.active.is_(True),
                )
                .values(active=False)
            )
            s.add(UserMemory(user_id=user_id, kind=kind, value=value, source=source, active=True))
            await s.commit()

    async def extract_from_plan(self, user_id: str, plan, brief: str) -> None:
        """Learn durable preferences from a successful plan. Conservative: only
        the stable production settings, each with the brief as its source."""
        src = (brief or "")[:160]
        await self.remember(user_id, "tone", plan.tone, src)
        await self.remember(user_id, "language", plan.language, src)
        await self.remember(user_id, "duration", str(plan.duration_seconds), src)

    async def delete_memory(self, user_id: str, memory_id: int) -> bool:
        async with self._sf() as s:
            row = await s.get(UserMemory, memory_id)
            if row is None or row.user_id != user_id:
                return False
            await s.execute(delete(UserMemory).where(UserMemory.id == memory_id))
            await s.commit()
            return True

    async def clear_memories(self, user_id: str) -> int:
        async with self._sf() as s:
            res = await s.execute(delete(UserMemory).where(UserMemory.user_id == user_id))
            await s.commit()
            return res.rowcount or 0

    async def view(self, user_id: str) -> MemoryView:
        return MemoryView(
            preferences=await self.get_preferences(user_id),
            memories=await self.recall(user_id),
        )


_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
