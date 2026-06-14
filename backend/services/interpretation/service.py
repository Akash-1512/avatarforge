"""Interpretation — how the app understood a film request, before it renders.

The new explicit step in the conversational studio: rather than jumping straight from
a raw prompt to a storyboard, the app first reads the whole request (cast, voices,
theme, script) and produces a structured, plain-language interpretation the user can
see and approve — "Here's the film I'm about to make: a {theme} short titled '{title}'
with {n} people; ARIA (your anime avatar, warm voice) opens, KAI responds…". Rendering
then proceeds against this interpretation, so the user is never surprised by what the
model decided.

Deterministic at the edges (title, beat count, who-does-what come from the cast +
script), with the LLM filling the narrative read. Degrades to a sensible template if
the LLM is unavailable, so the step never blocks the pipeline.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from backend.observability.logging import get_logger
from backend.services.llm.service import LLMService

logger = get_logger(__name__)

_INTERP_SYSTEM = (
    "You read a short-film request and explain, in 2-4 plain sentences, how you "
    "understand it: the premise, the mood/theme, who appears and what they do. "
    "Be concrete and faithful to the script and cast — invent nothing. Respond with "
    'STRICT JSON only: {"title": string, "premise": string, "beats": [string]}. '
    "beats is a short ordered list of what happens, one line each."
)


@dataclass
class Interpretation:
    title: str
    premise: str
    beats: List[str] = field(default_factory=list)
    cast_summary: List[dict] = field(default_factory=list)
    theme: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def human_readable(self) -> str:
        people = ", ".join(
            f"{c['role']} ("
            f"{c.get('style', 'realistic')}{'/real' if c.get('is_real_person') else ''})"
            for c in self.cast_summary
        )
        lines = [f"**{self.title}** — a {self.theme or 'cinematic'} short.", "", self.premise]
        if people:
            lines += ["", f"Cast: {people}."]
        if self.beats:
            lines += ["", "How it plays out:"] + [f"  {i+1}. {b}" for i, b in enumerate(self.beats)]
        return "\n".join(lines)


class InterpretationService:
    def __init__(self, llm: LLMService):
        self.llm = llm

    async def interpret(
        self, script: str, cast: List[dict], theme: Optional[str] = None
    ) -> Interpretation:
        cast_summary = [
            {
                "role": c.get("role", ""),
                "style": c.get("style", "realistic"),
                "is_real_person": c.get("is_real_person", False),
                "voice": c.get("voice", ""),
            }
            for c in cast
        ]
        roster = "; ".join(
            f"{c['role']} = {c['style']} {'real person' if c['is_real_person'] else 'stylized'}"
            f"{', voice: ' + c['voice'] if c['voice'] else ''}"
            for c in cast_summary
        )
        user = f"Theme: {theme or 'unspecified'}\nCast: {roster}\n\nScript:\n{script}"
        try:
            raw = await self.llm.complete_json_raw(_INTERP_SYSTEM, user)
            data = json.loads(raw)
            interp = Interpretation(
                title=str(data.get("title", "")).strip() or "Untitled",
                premise=str(data.get("premise", "")).strip(),
                beats=[str(b).strip() for b in data.get("beats", [])][:8],
                cast_summary=cast_summary,
                theme=theme or "",
            )
            if interp.premise:
                return interp
        except Exception as exc:  # noqa: BLE001 — fall back to a template
            logger.warning("interpretation_llm_failed", err=str(exc)[:160])

        # deterministic fallback so the step never blocks
        return Interpretation(
            title="Untitled Short",
            premise=(
                f"A {theme or 'cinematic'} short featuring "
                f"{len(cast_summary)} character(s), following the provided script."
            ),
            beats=[],
            cast_summary=cast_summary,
            theme=theme or "",
        )


def get_interpretation_service() -> InterpretationService:
    from backend.services.llm.service import get_llm_service

    return InterpretationService(get_llm_service())
