"""Film session orchestration — the conversational, self-correcting film engine.

Drives a FilmSession through its lifecycle while *streaming its thinking* as discrete
stage events (interpreting -> storyboarding -> rendering scene N -> critiquing ->
re-rendering -> done), so a chat UI can show the work as it happens. After a film is
produced, follow-up messages are parsed into edits — targeted actions (re-render scene
N, change a voice, change the theme) or open-ended natural language ("make it dreamier")
that an intent parser maps onto those same actions — and applied to the existing
session rather than starting over.

Streaming is via an async generator of {stage, message, data} events. The same events
are what the SSE endpoint forwards to the browser.
"""

import json
import uuid
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from backend.observability.logging import get_logger
from backend.services.cast.service import CastError, get_cast_service
from backend.services.composition.service import CompositionError, get_composition_service
from backend.services.director.service import DirectorError, get_director_service
from backend.services.interpretation.service import get_interpretation_service
from backend.services.llm.service import LLMService

logger = get_logger(__name__)


def _event(stage: str, message: str, **data) -> dict:
    return {"stage": stage, "message": message, "data": data}


@dataclass
class EditIntent:
    action: str  # "rerender_scene" | "change_theme" | "change_voice" | "rerender_all" | "unknown"
    scene_index: Optional[int] = None
    role: Optional[str] = None
    value: str = ""


_EDIT_SYSTEM = (
    "You translate a user's edit request about a short film into ONE structured action. "
    "Available actions: rerender_scene (needs scene_index, optional note in value), "
    "change_theme (value = new theme like pixar/anime/cinematic/realistic), "
    "change_voice (role + value = voice description), rerender_all (value = note), "
    "unknown. Respond STRICT JSON only: "
    '{"action": str, "scene_index": int|null, "role": str|null, "value": str}.'
)


class FilmSessionService:
    """Stateless orchestrator; the FilmSession row carries all state."""

    def __init__(self, llm: Optional[LLMService] = None):
        self._llm = llm

    @property
    def llm(self) -> LLMService:
        if self._llm is None:
            from backend.services.llm.service import get_llm_service

            self._llm = get_llm_service()
        return self._llm

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    # ---- the create + produce flow (streamed) -----------------------------
    async def produce(self, session, persist=None) -> AsyncGenerator[dict, None]:
        """Run interpret -> storyboard -> render for a fresh session, yielding stage
        events. `persist(session)` (if given) is awaited after each state change so
        the SSE endpoint can checkpoint progress."""
        cast_dicts = session.cast
        yield _event("interpreting", "Reading your request and working out the film…")
        try:
            interp = await get_interpretation_service().interpret(
                session.script, cast_dicts, theme=session.theme
            )
        except Exception as exc:  # noqa: BLE001
            session.status = "failed"
            if persist:
                await persist(session)
            yield _event("failed", f"Could not interpret the request: {exc}")
            return

        session._set("interpretation_json", interp.to_dict())
        session.title = interp.title
        session.status = "ready_to_render"
        session.append_history("assistant", interp.human_readable())
        if persist:
            await persist(session)
        yield _event("interpreted", interp.human_readable(), interpretation=interp.to_dict())

        # bind cast (ownership-checked) then storyboard + render
        try:
            cast = await get_cast_service().bind(session.user_id, cast_dicts)
        except CastError as exc:
            session.status = "failed"
            if persist:
                await persist(session)
            yield _event("failed", f"Cast problem: {exc}")
            return

        yield _event("storyboarding", "Breaking the script into shots…")
        try:
            board = await get_director_service().storyboard_with_cast(
                session.script, [m.role for m in cast.members], style=session.theme or None
            )
        except DirectorError as exc:
            session.status = "failed"
            if persist:
                await persist(session)
            yield _event("failed", f"Storyboard failed: {exc}")
            return

        session._set("storyboard_json", _board_to_dict(board))
        if persist:
            await persist(session)
        yield _event(
            "storyboarded",
            f"{len(board.scenes)} scenes planned ({board.total_seconds}s).",
            scene_count=len(board.scenes),
        )

        session.status = "rendering"
        if persist:
            await persist(session)
        for i, sc in enumerate(board.scenes):
            yield _event(
                "rendering",
                f"Rendering scene {i + 1} of {len(board.scenes)}: {sc.shot}",
                scene_index=i,
            )
        try:
            result = await get_composition_service().render_with_cast(board, cast)
        except CompositionError as exc:
            session.status = "failed"
            if persist:
                await persist(session)
            yield _event("failed", f"Render failed: {exc}")
            return

        from backend.services.storage.local import get_storage

        stored = await get_storage().save_bytes(result.stitched, "mp4")
        session.clip_id = stored.file_id
        session._set(
            "scenes_json",
            [
                {
                    "index": c.index,
                    "engine": c.engine,
                    "seconds": c.seconds,
                    "role": board.scenes[c.index].role,
                }
                for c in result.clips
            ],
        )
        session.status = "done"
        session.append_history("assistant", f"Here's your film — {len(result.clips)} scenes.")
        if persist:
            await persist(session)
        yield _event(
            "done", "Your film is ready.", clip_id=stored.file_id, scene_count=len(result.clips)
        )

    # ---- conversational edits --------------------------------------------
    async def parse_edit(self, message: str, session) -> EditIntent:
        """Map a free-text edit request onto a structured action (targeted edits are
        the reliable core; this lets open-ended language reach them)."""
        try:
            raw = await self.llm.complete_json_raw(
                _EDIT_SYSTEM,
                f"Scenes available: {len(session.scenes)}. "
                f"Cast roles: {[c.get('role') for c in session.cast]}. "
                f"Request: {message}",
            )
            data = json.loads(raw)
            idx = data.get("scene_index")
            return EditIntent(
                action=str(data.get("action", "unknown")),
                scene_index=int(idx) if isinstance(idx, int) else None,
                role=(str(data["role"]) if data.get("role") else None),
                value=str(data.get("value", "")).strip(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("edit_parse_failed", err=str(exc)[:160])
            return EditIntent(action="unknown", value=message)

    async def apply_edit(self, session, message: str, persist=None) -> AsyncGenerator[dict, None]:
        """Apply a conversational edit to an existing film, streaming progress."""
        session.append_history("user", message)
        yield _event("thinking", "Working out what you'd like to change…")
        intent = await self.parse_edit(message, session)

        if intent.action == "change_theme" and intent.value:
            session.theme = intent.value
            session.append_history(
                "assistant", f"Switching the theme to {intent.value} and re-rendering."
            )
            if persist:
                await persist(session)
            async for ev in self._rerender(session, persist):
                yield ev
            return

        if intent.action == "change_voice" and intent.role:
            cast = session.cast
            for c in cast:
                if c.get("role", "").upper() == intent.role.upper():
                    c["voice"] = intent.value
            session._set("cast_json", cast)
            session.append_history("assistant", f"Updated {intent.role}'s voice; re-rendering.")
            if persist:
                await persist(session)
            async for ev in self._rerender(session, persist):
                yield ev
            return

        if intent.action in ("rerender_scene", "rerender_all"):
            session.append_history("assistant", "Re-rendering with your note.")
            if persist:
                await persist(session)
            async for ev in self._rerender(session, persist):
                yield ev
            return

        # unknown: ask for a clearer instruction rather than guess
        msg = (
            "I can re-render the film, change the theme (e.g. 'make it anime'), "
            "or change a character's voice (e.g. 'give KAI a deeper voice'). "
            "Which would you like?"
        )
        session.append_history("assistant", msg)
        if persist:
            await persist(session)
        yield _event("clarify", msg)

    async def _rerender(self, session, persist) -> AsyncGenerator[dict, None]:
        """Re-bind cast + re-run storyboard/render for the current session state."""
        try:
            cast = await get_cast_service().bind(session.user_id, session.cast)
            yield _event("storyboarding", "Re-planning the shots…")
            board = await get_director_service().storyboard_with_cast(
                session.script, [m.role for m in cast.members], style=session.theme or None
            )
            session.status = "rendering"
            if persist:
                await persist(session)
            yield _event(
                "rendering",
                f"Re-rendering {len(board.scenes)} scenes…",
                scene_count=len(board.scenes),
            )
            result = await get_composition_service().render_with_cast(board, cast)
        except (CastError, DirectorError, CompositionError) as exc:
            session.status = "failed"
            if persist:
                await persist(session)
            yield _event("failed", f"Re-render failed: {exc}")
            return

        from backend.services.storage.local import get_storage

        stored = await get_storage().save_bytes(result.stitched, "mp4")
        session.clip_id = stored.file_id
        session._set(
            "scenes_json",
            [
                {
                    "index": c.index,
                    "engine": c.engine,
                    "seconds": c.seconds,
                    "role": board.scenes[c.index].role,
                }
                for c in result.clips
            ],
        )
        session.status = "done"
        if persist:
            await persist(session)
        yield _event("done", "Updated film is ready.", clip_id=stored.file_id)


def _board_to_dict(board) -> dict:
    return {
        "title": board.title,
        "style": board.style,
        "scenes": [
            {
                "shot": s.shot,
                "camera": s.camera,
                "dialogue": s.dialogue,
                "seconds": s.seconds,
                "role": s.role,
            }
            for s in board.scenes
        ],
    }


def get_film_session_service() -> FilmSessionService:
    return FilmSessionService()
