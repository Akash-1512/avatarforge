"""Director agent — turn a brief into a structured Storyboard.

A film is not one prompt; it is an ordered list of scenes, each with a shot
description, camera, optional dialogue, and a duration. The director is a sibling
of the planner: it reuses LLMService.complete_json_raw (inheriting the Azure->OpenAI
fallback and circuit breakers) to produce that structure from a one-line brief, then
validates and clamps it into a Storyboard the composition layer can fan out over.

Kept deliberately deterministic at the edges: scene count, per-scene seconds, and
total runtime are clamped to the achievable target (cinematic shorts, not features),
so a hallucinated 20-scene 10-minute plan can't reach the render path.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional

from backend.observability.logging import get_logger
from backend.services.llm.service import LLMService, get_llm_service

logger = get_logger(__name__)

MAX_SCENES = 8
MIN_SCENES = 1
MIN_SCENE_SECONDS = 2
MAX_SCENE_SECONDS = 10
MAX_TOTAL_SECONDS = 60

_DIRECTOR_SYSTEM = """You are a film director. Turn the user's brief into a short \
cinematic storyboard as STRICT JSON only (no prose, no markdown).

Schema:
{
  "title": string,
  "style": one of ["realistic","anime","pixar","3d","claymation","watercolor"],
  "scenes": [
    {
      "shot": string,         // what we see: subject, action, setting
      "camera": string,       // e.g. "slow push-in", "wide static", "tracking left"
      "dialogue": string,     // spoken line, or "" if none
      "seconds": integer      // 2-10
    }
  ]
}

Rules: 1 to 8 scenes. Keep total runtime <= 60 seconds. Every scene must read as a \
distinct shot that advances the brief. If the brief implies a character speaking, \
put their words in "dialogue". Output JSON only."""


@dataclass
class Scene:
    shot: str
    camera: str
    dialogue: str
    seconds: int
    role: str = ""  # which cast role appears in this shot (empty = no specific person)


@dataclass
class Storyboard:
    title: str
    style: str
    scenes: List[Scene] = field(default_factory=list)

    @property
    def total_seconds(self) -> int:
        return sum(s.seconds for s in self.scenes)


class DirectorError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


_DIRECTOR_CAST_SYSTEM = _DIRECTOR_SYSTEM.replace(
    "Output JSON only.",
    'Each scene also has a "role" naming the single cast member on screen '
    "(must be one of the provided cast roles, or empty). Output JSON only.",
).replace(
    '"seconds": integer      // 2-10',
    '"seconds": integer,     // 2-10\n'
    '      "role": string          // a cast role on screen, or ""',
)

_VALID_STYLES = {"realistic", "anime", "pixar", "3d", "claymation", "watercolor"}


class DirectorService:
    def __init__(self, llm: LLMService):
        self.llm = llm

    async def storyboard(self, brief: str, style: Optional[str] = None) -> Storyboard:
        raw = await self.llm.complete_json_raw(_DIRECTOR_SYSTEM, f"Brief: {brief}")
        board = self._parse(raw)
        if board is None:
            # one structured retry, same pattern the planner uses
            raw = await self.llm.complete_json_raw(
                _DIRECTOR_SYSTEM, f"Return ONLY valid JSON for this brief: {brief}"
            )
            board = self._parse(raw)
        if board is None:
            raise DirectorError("Director could not produce a valid storyboard")
        if style:
            board.style = style if style in _VALID_STYLES else board.style
        return self._clamp(board)

    async def storyboard_with_cast(
        self, script: str, roles: list[str], style: Optional[str] = None
    ) -> Storyboard:
        """Plan a storyboard from a script + the cast's role names, tagging each
        scene with the role on screen so composition can route per person."""
        roster = ", ".join(roles) if roles else "(none)"
        user = (
            f"Cast roles: {roster}.\n"
            f'For each scene set "role" to the single cast role on screen '
            f"(one of the cast roles, or empty if none).\n\nScript:\n{script}"
        )
        raw = await self.llm.complete_json_raw(_DIRECTOR_CAST_SYSTEM, user)
        board = self._parse(raw)
        if board is None:
            raw = await self.llm.complete_json_raw(
                _DIRECTOR_CAST_SYSTEM, "Return ONLY valid JSON. " + user
            )
            board = self._parse(raw)
        if board is None:
            raise DirectorError("Director could not produce a valid storyboard")
        # keep only roles that exist in the cast; blank out hallucinated names
        valid = {r.upper() for r in roles}
        for s in board.scenes:
            if s.role and s.role.upper() not in valid:
                s.role = ""
        if style:
            board.style = style if style in _VALID_STYLES else board.style
        return self._clamp(board)

    @staticmethod
    def _parse(raw: str) -> Optional[Storyboard]:
        try:
            data = json.loads(raw)
            scenes = [
                Scene(
                    shot=str(s.get("shot", "")).strip(),
                    camera=str(s.get("camera", "")).strip(),
                    dialogue=str(s.get("dialogue", "")).strip(),
                    seconds=int(s.get("seconds", 5)),
                    role=str(s.get("role", "")).strip(),
                )
                for s in data.get("scenes", [])
                if str(s.get("shot", "")).strip()
            ]
            if not scenes:
                return None
            style = data.get("style", "realistic")
            return Storyboard(
                title=str(data.get("title", "Untitled")).strip()[:120],
                style=style if style in _VALID_STYLES else "realistic",
                scenes=scenes,
            )
        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def _clamp(board: Storyboard) -> Storyboard:
        """Clamp to the achievable target so a hallucinated plan can't reach render."""
        board.scenes = board.scenes[:MAX_SCENES]
        for s in board.scenes:
            s.seconds = max(MIN_SCENE_SECONDS, min(MAX_SCENE_SECONDS, s.seconds))
        # trim trailing scenes if total runtime overflows the cap
        total = 0
        kept: List[Scene] = []
        for s in board.scenes:
            if total + s.seconds > MAX_TOTAL_SECONDS:
                break
            total += s.seconds
            kept.append(s)
        board.scenes = kept or board.scenes[:1]
        return board


def get_director_service() -> DirectorService:
    return DirectorService(get_llm_service())
