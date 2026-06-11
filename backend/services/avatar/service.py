"""AvatarService — validate inputs, run inference, package, store, audit.

No provider fallback here (there is exactly one engine); the resilience
patterns are input validation, timeout normalization, and best-effort
auditing. Synchronous in Phase 4; Phase 5 moves this behind Celery.
"""

import time
from functools import lru_cache
from typing import Awaitable, Callable, Optional

from backend.config import get_settings
from backend.models.schemas import AvatarResponse
from backend.observability.logging import get_logger
from backend.services.avatar.client import AvatarEngineError, SadTalkerClient
from backend.services.avatar.postprocess import package_mp4, probe_video
from backend.services.avatar.validation import validate_source_image
from backend.services.storage.base import BaseStorageBackend
from backend.services.storage.local import get_storage

logger = get_logger(__name__)

UsageRecorder = Callable[[dict], Awaitable[None]]


class AvatarService:
    def __init__(
        self,
        client: SadTalkerClient,
        storage: BaseStorageBackend,
        usage_recorder: Optional[UsageRecorder] = None,
    ):
        self.client = client
        self.storage = storage
        self.usage_recorder = usage_recorder

    async def _record(self, payload: dict) -> None:
        if self.usage_recorder is None:
            return
        try:
            await self.usage_recorder(payload)
        except Exception as exc:  # noqa: BLE001 — auditing is best-effort
            logger.warning("avatar_usage_record_failed", error=str(exc))

    async def generate(
        self,
        image_bytes: bytes,
        audio_file_id: str,
        *,
        preprocess: str = "crop",
        enhancer: bool = False,
    ) -> AvatarResponse:
        image_ext = validate_source_image(image_bytes)

        audio_path = self.storage.resolve_path(audio_file_id)
        if audio_path is None or not audio_file_id.endswith(".wav"):
            raise FileNotFoundError(
                f"Audio file '{audio_file_id}' not found. Generate it first via /tts/synthesize."
            )
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        started = time.monotonic()
        try:
            raw_video = await self.client.infer(
                image_bytes,
                image_ext,
                audio_bytes,
                preprocess=preprocess,
                enhancer=enhancer,
            )
            packaged = await package_mp4(raw_video)
            meta = await probe_video(packaged)
            stored = await self.storage.save_bytes(packaged, "mp4")
            latency_ms = int((time.monotonic() - started) * 1000)

            await self._record(
                {
                    "audio_file_id": audio_file_id,
                    "preprocess": preprocess,
                    "enhancer": enhancer,
                    "video_duration_sec": meta["duration_sec"],
                    "latency_ms": latency_ms,
                    "success": True,
                    "error_type": None,
                }
            )
            logger.info(
                "avatar_generated",
                duration_sec=meta["duration_sec"],
                latency_ms=latency_ms,
                resolution=f"{meta['width']}x{meta['height']}",
            )
            return AvatarResponse(
                video_url=stored.url,
                file_id=stored.file_id,
                video_duration_sec=meta["duration_sec"],
                width=meta["width"],
                height=meta["height"],
                codec=meta["codec"],
                latency_ms=latency_ms,
                preprocess=preprocess,
                enhancer=enhancer,
            )
        except AvatarEngineError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            await self._record(
                {
                    "audio_file_id": audio_file_id,
                    "preprocess": preprocess,
                    "enhancer": enhancer,
                    "video_duration_sec": 0.0,
                    "latency_ms": latency_ms,
                    "success": False,
                    "error_type": type(exc).__name__,
                }
            )
            logger.warning("avatar_generation_failed", error=str(exc)[:300])
            raise


async def _db_usage_recorder(payload: dict) -> None:
    from backend.models.avatar_usage import AvatarUsage
    from backend.models.db import get_session_factory

    async with get_session_factory()() as session:
        session.add(AvatarUsage(**payload))
        await session.commit()


@lru_cache
def get_avatar_service() -> AvatarService:
    settings = get_settings()
    return AvatarService(
        client=SadTalkerClient(settings),
        storage=get_storage(),
        usage_recorder=_db_usage_recorder,
    )
