"""Character service — create, list, fetch, and delete character assets.

Orchestrates ingest (photo/video/live -> reference frames) and persistence. Like
the job repository, it resolves the session factory lazily so a Celery task that
reset its engine is honoured, and tests can inject a SQLite factory.
"""

import uuid
from typing import Optional

from sqlalchemy import delete, select

from backend.models.character import Character
from backend.observability.logging import get_logger
from backend.services.character.ingest import CharacterIngestService, IngestError
from backend.services.storage.local import get_storage

logger = get_logger(__name__)

_VALID_STYLES = {"realistic", "anime", "pixar", "3d", "claymation", "watercolor"}


class CharacterService:
    def __init__(self, session_factory=None, ingest: Optional[CharacterIngestService] = None):
        self._injected = session_factory
        self._ingest = ingest or CharacterIngestService(get_storage())

    @property
    def _sf(self):
        if self._injected is not None:
            return self._injected
        from backend.models.db import get_session_factory

        return get_session_factory()

    async def create(
        self,
        user_id: str,
        name: str,
        source_bytes: bytes,
        source_kind: str = "photo",
        default_style: str = "realistic",
        is_real_person: bool = True,
    ) -> Character:
        if default_style not in _VALID_STYLES:
            raise IngestError(f"Unknown style '{default_style}'. Allowed: {sorted(_VALID_STYLES)}")

        if source_kind == "photo":
            result = await self._ingest.ingest_photo(source_bytes)
        elif source_kind in ("video", "live"):
            result = await self._ingest.ingest_video(source_bytes)
        else:
            raise IngestError(f"Unknown source_kind '{source_kind}'")

        char = Character(
            id=uuid.uuid4().hex,
            user_id=user_id,
            name=name[:120] or "Untitled character",
            source_kind=source_kind,
            reference_frame_ids=",".join(result.frame_ids),
            default_style=default_style,
            is_real_person=is_real_person,
            status="ready",
            frame_count=result.frame_count,
        )
        async with self._sf() as s:
            s.add(char)
            await s.commit()
            await s.refresh(char)
        logger.info(
            "character_created", character_id=char.id, frames=char.frame_count, style=default_style
        )
        return char

    async def get(self, character_id: str) -> Optional[Character]:
        async with self._sf() as s:
            return await s.get(Character, character_id)

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[Character]:
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(Character)
                        .where(Character.user_id == user_id)
                        .order_by(Character.created_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    async def delete(self, user_id: str, character_id: str) -> bool:
        async with self._sf() as s:
            row = await s.get(Character, character_id)
            if row is None or row.user_id != user_id:
                return False
            await s.execute(delete(Character).where(Character.id == character_id))
            await s.commit()
            return True


_character_service: Optional[CharacterService] = None


def get_character_service() -> CharacterService:
    global _character_service
    if _character_service is None:
        _character_service = CharacterService()
    return _character_service
