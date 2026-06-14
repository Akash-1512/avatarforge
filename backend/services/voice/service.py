"""Voiceover — turn a line of dialogue into audio bytes for a cast role.

Thin wrapper over the existing TTS provider chain (Azure -> OpenAI -> ElevenLabs)
that returns raw audio bytes for a given line + voice preset, so the composition
layer can lip-sync it onto a character's scene. The per-role `voice` string is
passed through as the provider voice preset (an ElevenLabs voice id, an Azure voice
name, or — resolved in the described-voice step — a synthesized voice).

Resilient by design: callers treat a None return as "no voiceover for this scene"
and keep the silent clip, so a TTS hiccup never fails an entire film.
"""

from typing import Optional

from backend.observability.logging import get_logger
from backend.services.tts.base import AllTTSProvidersFailedError

logger = get_logger(__name__)


class VoiceoverService:
    def __init__(self, providers=None):
        # default to the same provider chain the TTS service builds
        if providers is None:
            from backend.services.tts.service import get_tts_service

            providers = get_tts_service().providers
        self.providers = providers

    async def speak(self, text: str, voice: str = "", language: str = "en") -> Optional[bytes]:
        """Synthesize one line; return audio bytes, or None if nothing is available.

        `voice` may be an explicit preset/voice id OR a plain-language description
        ("a warm, unhurried baritone") — descriptions are resolved to a concrete
        voice first, so the cast can describe voices in words.
        """
        if not text.strip():
            return None
        resolved = voice
        if voice and not self._looks_like_id(voice):
            try:
                from backend.services.voice.resolver import get_voice_resolver

                resolved = await get_voice_resolver().resolve(voice, language=language)
            except Exception as exc:  # noqa: BLE001 — fall back to the raw string
                logger.warning("voice_resolve_skipped", err=str(exc)[:160])
                resolved = voice
        for provider in self.providers:
            if not getattr(provider, "available", False):
                continue
            try:
                result = await provider.synthesize(
                    text, voice_preset=resolved or None, language=language
                )
                if result and result.audio_bytes:
                    return result.audio_bytes
            except Exception as exc:  # noqa: BLE001 — try the next provider
                logger.warning(
                    "voiceover_provider_failed", provider=provider.name, err=str(exc)[:160]
                )
                continue
        return None

    @staticmethod
    def _looks_like_id(value: str) -> bool:
        """A provider voice id / preset (skip resolution) vs a description."""
        import re

        v = value.strip()
        return (
            bool(re.match(r"^[a-z]{2}-[A-Z]{2}-\w+$", v))  # en-US-JennyNeural
            or v in {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
            or (len(v.split()) == 1 and "_" in v)  # role token like professional_male
        )


def get_voiceover_service() -> VoiceoverService:
    try:
        return VoiceoverService()
    except AllTTSProvidersFailedError:
        return VoiceoverService(providers=[])
