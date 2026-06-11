"""TTSService — Azure Speech → OpenAI TTS fallback with circuit breaking.

Output contract regardless of provider: a stored WAV file at 16kHz mono,
loudness-normalized (SadTalker's input spec), addressable via /api/v1/media.
Azure F0 synthesis is free; OpenAI tts-1 costs $15 per 1M characters.
"""

import time
from functools import lru_cache
from typing import Awaitable, Callable, List, Optional

from backend.config import get_settings
from backend.models.schemas import TTSRequest, TTSResponse
from backend.observability.logging import get_logger
from backend.services.common.circuit_breaker import CircuitBreaker
from backend.services.storage.base import BaseStorageBackend
from backend.services.storage.local import get_storage
from backend.services.tts.audio import normalize_to_sadtalker_spec, wav_duration_seconds
from backend.services.tts.base import AllTTSProvidersFailedError, BaseTTSProvider, TTSProviderError
from backend.services.tts.providers import AzureSpeechProvider, OpenAITTSProvider

logger = get_logger(__name__)

# USD per character
_COST_PER_CHAR = {"azure_speech": 0.0, "openai_tts": 15.0 / 1_000_000}

UsageRecorder = Callable[[dict], Awaitable[None]]


class TTSService:
    def __init__(
        self,
        providers: List[BaseTTSProvider],
        storage: BaseStorageBackend,
        usage_recorder: Optional[UsageRecorder] = None,
        failure_threshold: int = 3,
        recovery_timeout_sec: float = 300.0,
    ):
        self.providers = providers
        self.storage = storage
        self.usage_recorder = usage_recorder
        self.breakers = {
            p.name: CircuitBreaker(failure_threshold, recovery_timeout_sec) for p in providers
        }

    async def _record(self, payload: dict) -> None:
        if self.usage_recorder is None:
            return
        try:
            await self.usage_recorder(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tts_usage_record_failed", error=str(exc))

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        last_error: Exception | None = None

        for provider in self.providers:
            if not provider.available:
                logger.info("tts_provider_skipped_unconfigured", provider=provider.name)
                continue

            breaker = self.breakers[provider.name]
            if not breaker.allow_request():
                logger.warning("tts_provider_skipped_circuit_open", provider=provider.name)
                continue

            started = time.monotonic()
            try:
                result = await provider.synthesize(
                    request.text, request.voice, request.speaking_rate
                )
                normalized = await normalize_to_sadtalker_spec(result.audio_bytes)
                duration = wav_duration_seconds(normalized)
                stored = await self.storage.save_bytes(normalized, "wav")
                latency_ms = int((time.monotonic() - started) * 1000)
                breaker.record_success()

                cost = round(result.characters * _COST_PER_CHAR.get(provider.name, 0.0), 6)
                await self._record(
                    {
                        "provider": provider.name,
                        "model": result.model,
                        "voice_preset": request.voice,
                        "characters": result.characters,
                        "estimated_cost_usd": cost,
                        "audio_duration_sec": duration,
                        "latency_ms": latency_ms,
                        "success": True,
                        "error_type": None,
                    }
                )
                logger.info(
                    "tts_synthesized",
                    provider=provider.name,
                    voice=request.voice,
                    duration_sec=duration,
                    latency_ms=latency_ms,
                )
                return TTSResponse(
                    audio_url=stored.url,
                    file_id=stored.file_id,
                    provider_used=provider.name,
                    model=result.model,
                    voice=request.voice,
                    characters=result.characters,
                    audio_duration_sec=duration,
                    latency_ms=latency_ms,
                    estimated_cost_usd=cost,
                    format="wav 16kHz mono (SadTalker-ready)",
                )

            except TTSProviderError as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                breaker.record_failure()
                last_error = exc
                await self._record(
                    {
                        "provider": provider.name,
                        "model": "unknown",
                        "voice_preset": request.voice,
                        "characters": len(request.text),
                        "estimated_cost_usd": 0.0,
                        "audio_duration_sec": 0.0,
                        "latency_ms": latency_ms,
                        "success": False,
                        "error_type": type(exc.original).__name__,
                    }
                )
                logger.warning(
                    "tts_provider_failed_falling_back",
                    provider=provider.name,
                    error=str(exc)[:200],
                )

        raise AllTTSProvidersFailedError(
            f"No TTS provider could synthesize speech. Last error: {last_error}"
        )


async def _db_usage_recorder(payload: dict) -> None:
    from backend.models.db import get_session_factory
    from backend.models.tts_usage import TTSUsage

    async with get_session_factory()() as session:
        session.add(TTSUsage(**payload))
        await session.commit()


@lru_cache
def get_tts_service() -> TTSService:
    settings = get_settings()
    return TTSService(
        providers=[AzureSpeechProvider(settings), OpenAITTSProvider(settings)],
        storage=get_storage(),
        usage_recorder=_db_usage_recorder,
    )
