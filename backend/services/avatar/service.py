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
    """Routes generation requests to a registry of engines.

    Engines share one HTTP contract, so a single client class serves all of
    them; the registry maps engine name -> configured client. Requesting an
    engine that isn't configured is a 503-class error, not a crash.
    """

    def __init__(
        self,
        engines: dict[str, SadTalkerClient],
        storage: BaseStorageBackend,
        usage_recorder: Optional[UsageRecorder] = None,
        default_engine: str = "sadtalker",
    ):
        self.engines = engines
        self.storage = storage
        self.usage_recorder = usage_recorder
        self.default_engine = default_engine

    @property
    def client(self) -> SadTalkerClient:
        """Default-engine client (kept for health checks and back-compat)."""
        return self.engines[self.default_engine]

    def resolve_engine(self, engine: Optional[str]) -> tuple[str, SadTalkerClient]:
        name = engine or self.default_engine
        client = self.engines.get(name)
        if client is None:
            raise AvatarEngineError(
                f"Avatar engine '{name}' is not configured. " f"Available: {sorted(self.engines)}",
                status_code=503,
            )
        return name, client

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
        engine: Optional[str] = None,
    ) -> AvatarResponse:
        engine_name, client = self.resolve_engine(engine)
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
            raw_video = await client.infer(
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
                engine=engine_name,
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
                engine=engine_name,
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
    engines: dict = {"sadtalker": SadTalkerClient(settings)}
    if settings.hunyuan_url:
        engines["hunyuan"] = SadTalkerClient(settings, base_url=settings.hunyuan_url)
    if settings.fal_api_key:
        from backend.services.avatar.fal_client import FalAvatarClient

        engines["fal"] = FalAvatarClient(settings)
    return AvatarService(
        engines=engines,
        storage=get_storage(),
        usage_recorder=_db_usage_recorder,
        default_engine=settings.avatar_default_engine,
    )
