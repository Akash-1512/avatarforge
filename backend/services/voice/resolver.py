"""Described-voice synthesis — turn "a warm, unhurried baritone" into a real voice.

The cast lets a user *describe* a voice in plain words instead of knowing a preset id.
This resolver reads a free-text description and maps it onto one of the available
voice roles (professional/casual × female/male, or narrator), which the existing
preset matrix then turns into a concrete Azure/OpenAI voice for the right language.

It's deliberately a mapping onto the curated preset catalogue rather than synthesising
a brand-new voice per request: it's deterministic, costs nothing extra, and never
fails a render. (A future enhancement could call a voice-design API to mint a bespoke
voice from the description; this resolver is the dependable baseline.)

A description that's already a known preset id or role passes straight through, so the
field accepts either a description or an explicit voice.
"""

import json
import re
from typing import Optional

from backend.observability.logging import get_logger
from backend.services.llm.service import LLMService
from backend.services.tts.voices import VOICE_MATRIX, resolve_voice

logger = get_logger(__name__)

_KNOWN_ROLES = set(VOICE_MATRIX.keys())

_RESOLVE_SYSTEM = (
    "Map a plain-language voice description to ONE voice role and its attributes. "
    "Roles: professional_female, professional_male, casual_female, casual_male, narrator. "
    "Pick the closest. Respond STRICT JSON only: "
    '{"role": str, "gender": "female"|"male"|"neutral", "tone": str}. '
    "tone is one or two words (e.g. warm, authoritative, bright)."
)

# fast keyword fallback when the LLM is unavailable — covers the common cases.
_MALE = re.compile(r"\b(male|man|baritone|bass|deep|masculine|guy|he|his)\b", re.I)
_FEMALE = re.compile(r"\b(female|woman|soprano|alto|feminine|she|her)\b", re.I)
_NARRATOR = re.compile(r"\b(narrat|documentary|voiceover|voice-over|story)\b", re.I)
_CASUAL = re.compile(r"\b(casual|friendly|warm|relaxed|conversational|playful|young)\b", re.I)


class VoiceResolver:
    def __init__(self, llm: Optional[LLMService] = None):
        self._llm = llm

    @property
    def llm(self) -> LLMService:
        if self._llm is None:
            from backend.services.llm.service import get_llm_service

            self._llm = get_llm_service()
        return self._llm

    @staticmethod
    def _is_preset(value: str) -> bool:
        v = value.strip()
        # an explicit role, or a provider voice id (e.g. en-US-JennyNeural, or "nova")
        return (
            v in _KNOWN_ROLES
            or bool(re.match(r"^[a-z]{2}-[A-Z]{2}-\w+$", v))
            or v
            in {
                "alloy",
                "echo",
                "fable",
                "onyx",
                "nova",
                "shimmer",
            }
        )

    def _fallback_role(self, text: str) -> str:
        if _NARRATOR.search(text):
            return "narrator"
        female = bool(_FEMALE.search(text))
        male = bool(_MALE.search(text))
        casual = bool(_CASUAL.search(text))
        if male and not female:
            return "casual_male" if casual else "professional_male"
        if female and not male:
            return "casual_female" if casual else "professional_female"
        # ambiguous gender -> narrator is the safest neutral default
        return "narrator"

    async def resolve(self, description: str, language: str = "en") -> str:
        """Return a concrete provider voice id for a description (or pass a preset
        straight through). Always returns something usable."""
        desc = (description or "").strip()
        if not desc:
            return resolve_voice("narrator", language).azure_voice
        if self._is_preset(desc):
            # already a role -> resolve to a concrete voice; already a voice id -> keep
            if desc in _KNOWN_ROLES:
                return resolve_voice(desc, language).azure_voice
            return desc

        role = await self._role_from_description(desc)
        preset = resolve_voice(role, language)
        logger.info("voice_described", desc=desc[:60], role=role, voice=preset.azure_voice)
        return preset.azure_voice

    async def role_for(self, description: str) -> str:
        """Expose the resolved role (used by tests and the cast summary)."""
        desc = (description or "").strip()
        if desc in _KNOWN_ROLES:
            return desc
        return await self._role_from_description(desc)

    async def _role_from_description(self, desc: str) -> str:
        try:
            raw = await self.llm.complete_json_raw(_RESOLVE_SYSTEM, desc)
            data = json.loads(raw)
            role = str(data.get("role", "")).strip()
            if role in _KNOWN_ROLES:
                return role
        except Exception as exc:  # noqa: BLE001 — fall back to keywords
            logger.warning("voice_resolve_llm_failed", err=str(exc)[:160])
        return self._fallback_role(desc)


def get_voice_resolver() -> VoiceResolver:
    return VoiceResolver()
