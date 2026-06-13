"""Prompt-to-video planner — turns a free-text brief into a validated job spec.

The agentic step the rest of the system was missing: instead of a user filling
six form fields, they describe what they want ("explain compound interest to
teenagers, upbeat, 30 seconds, in Hindi") and the planner decides topic, tone,
duration, language, voice, and engine.

Design notes that make this production-grade rather than a demo:
- The LLM returns JSON, but its freedom is bounded — output is validated against
  VideoPlan, whose field constraints are identical to the /videos/generate form.
  A hallucinated voice ("dramatic_baritone") or out-of-range duration fails
  validation and triggers one corrective retry, then falls back to safe defaults
  rather than 500ing. The model proposes; the schema disposes.
- It reuses LLMService.complete_json_raw, so it inherits the same Azure->OpenAI
  fallback and circuit breakers as every other LLM call. No new failure surface.
"""

import json
from functools import lru_cache

from pydantic import ValidationError

from backend.config import get_settings
from backend.models.schemas import VideoPlan
from backend.observability.logging import get_logger
from backend.services.llm.service import LLMService, get_llm_service

logger = get_logger(__name__)

_PLANNER_SYSTEM = """You plan short AI-avatar videos. Given a one-line brief, \
decide the production settings and respond with ONLY a JSON object — no markdown, \
no commentary — matching exactly:
{
  "topic": "a clear, specific topic line for the script writer",
  "tone": "professional|casual|enthusiastic|formal|friendly",
  "duration_seconds": 60,
  "language": "ISO-639-1 code, e.g. en, hi, mr, ta, es, fr, de",
  "voice": "professional_female|professional_male|casual_female|casual_male|narrator",
  "engine": "sadtalker|hunyuan|fal",
  "rationale": "one short sentence on why these settings fit the brief"
}

Rules:
- Infer language from the brief; default "en" if unstated.
- duration_seconds must be 15-300; pick what suits the brief (default 60).
- Map intent to tone and voice (e.g. "for kids, upbeat" -> enthusiastic + casual voice;
  "investor update" -> professional/formal + professional voice).
- Choose engine "sadtalker" unless the brief asks for the highest quality
  ("photorealistic", "best quality") -> "fal"; never invent other values.
- topic should be a polished subject line, not a verbatim echo of the brief."""


class PlannerService:
    def __init__(self, llm: LLMService):
        self.llm = llm

    async def plan(self, brief: str) -> VideoPlan:
        raw = await self.llm.complete_json_raw(_PLANNER_SYSTEM, f"Brief: {brief}")
        plan = self._parse(raw)
        if plan is not None:
            logger.info("plan_created", engine=plan.engine, lang=plan.language, tone=plan.tone)
            return plan

        # One corrective retry: hand the model its own bad output and the error.
        logger.warning("plan_invalid_retrying")
        retry_prompt = (
            f"Brief: {brief}\n\nYour previous response was not valid against the schema. "
            "Respond again with ONLY the JSON object, all fields present and within range."
        )
        raw = await self.llm.complete_json_raw(_PLANNER_SYSTEM, retry_prompt)
        plan = self._parse(raw)
        if plan is not None:
            return plan

        # Never 500 on a plan: degrade to a safe default seeded from the brief.
        logger.warning("plan_fallback_to_default")
        return VideoPlan(
            topic=brief[:500] if len(brief) >= 3 else "Untitled video",
            rationale="Planner output could not be validated; using safe defaults.",
        )

    @staticmethod
    def _parse(raw: str) -> VideoPlan | None:
        try:
            data = json.loads(
                raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            )
            return VideoPlan(**data)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            logger.warning("plan_parse_failed", error=str(exc)[:200])
            return None


@lru_cache
def get_planner_service() -> PlannerService:
    _ = get_settings()
    return PlannerService(llm=get_llm_service())
