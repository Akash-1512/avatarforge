"""Kling scene engine — reference-capable image/text-to-video on fal.

The complement to Sora 2: Kling accepts a real human-face reference and locks
identity across the shot (Kling Character-ID), so it serves the real-person route
that Azure Sora 2 rejects by policy. It speaks fal's queue protocol — the same
submit/poll/result pattern the avatar FalAvatarClient already uses — so this reuses
that hard-won knowledge (base64 data-URI inputs, HTTP 202 IN_QUEUE vs 200 COMPLETED,
authoritative `status` field, `video.url` in the result body).

This is the Phase-1 seam: the client is wired and routed, with the concrete fal
model endpoint pinned in a later phase once the reference-to-video shot list lands.
"""

from typing import Optional

from backend.config import Settings
from backend.observability.logging import get_logger
from backend.services.scene.sora2_client import SceneEngineError

logger = get_logger(__name__)


class KlingSceneClient:
    """Reference-capable scene engine (accepts real faces) on fal."""

    name = "kling"
    accepts_real_face = True  # registry routing signal

    def __init__(self, settings: Settings, api_key: Optional[str] = None):
        self._api_key = api_key or settings.fal_api_key
        self._timeout = settings.avatar_inference_timeout_sec

    def configured(self) -> bool:
        return bool(self._api_key)

    async def health(self) -> dict:
        return {"engine": self.name, "configured": self.configured(), "accepts_real_face": True}

    async def generate(self, prompt: str, seconds: int = 5, size: str = "1280x720") -> bytes:
        if not self.configured():
            raise SceneEngineError("Kling (fal) not configured: FAL_API_KEY missing", 503)
        # The fal submit/poll/result mechanics are identical to FalAvatarClient;
        # the concrete fal-ai/kling endpoint + reference-frame conditioning is wired
        # in Phase 3 (multi-scene shot list). Until then this engine is registered
        # and routable but not invoked for production renders.
        raise SceneEngineError(
            "Kling reference engine is registered but not yet enabled for rendering "
            "(arrives with the Phase 3 shot list).",
            status_code=501,
        )
