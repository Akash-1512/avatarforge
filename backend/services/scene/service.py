"""Scene engine registry — choose an engine by content policy, then cost/style.

The product can render a scene from a text prompt, optionally conditioned on a
character's reference frames. The constraint that drives routing: some engines
reject real human faces (Azure Sora 2), while reference-capable engines on fal
(Kling) accept a face reference for identity-locked shots. So the registry's
first decision is *content policy*, not price:

- A scene with NO real-person reference  -> Sora 2 (text-to-scene, on Azure).
- A scene WITH a real-person reference    -> a reference-capable engine (Kling/fal).

This mirrors the avatar-engine registry: engines share a thin contract, the
registry maps name -> client, and requesting an unconfigured engine is a
503-class error rather than a crash.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from backend.config import get_settings
from backend.observability.logging import get_logger
from backend.services.scene.sora2_client import SceneEngineError, Sora2SceneClient

logger = get_logger(__name__)


@dataclass
class SceneRequest:
    prompt: str
    seconds: int = 5
    size: str = "1280x720"
    has_real_face_reference: bool = False
    engine: Optional[str] = None  # explicit override; else routed
    reference_image: Optional[bytes] = None  # the character frame for reference engines


class SceneService:
    def __init__(self, engines: dict, default_engine: str = "sora2"):
        self.engines = engines
        self.default_engine = default_engine

    def route(self, req: SceneRequest) -> str:
        """Pick an engine name for this request, honouring content policy."""
        if req.engine:
            return req.engine
        if req.has_real_face_reference:
            # real faces must go to a reference-capable engine that accepts them
            for name, client in self.engines.items():
                if getattr(client, "accepts_real_face", False):
                    return name
            raise SceneEngineError(
                "No configured engine accepts a real human-face reference. "
                "Configure a reference-capable engine (e.g. Kling on fal).",
                status_code=503,
            )
        return self.default_engine

    def resolve(self, name: str):
        client = self.engines.get(name)
        if client is None:
            raise SceneEngineError(
                f"Scene engine '{name}' is not configured. Available: {sorted(self.engines)}",
                status_code=503,
            )
        return client

    async def generate(self, req: SceneRequest) -> bytes:
        name = self.route(req)
        client = self.resolve(name)
        logger.info("scene_generate", engine=name, seconds=req.seconds, size=req.size)
        # reference-capable engines (Kling) take the character frame; others ignore it
        if getattr(client, "accepts_real_face", False) and req.reference_image is not None:
            return await client.generate(
                req.prompt,
                seconds=req.seconds,
                size=req.size,
                reference_image=req.reference_image,
            )
        return await client.generate(req.prompt, seconds=req.seconds, size=req.size)

    def available(self) -> dict:
        return {
            "engines": sorted(self.engines),
            "default": self.default_engine,
            "real_face_capable": [
                n for n, c in self.engines.items() if getattr(c, "accepts_real_face", False)
            ],
        }


@lru_cache
def get_scene_service() -> SceneService:
    settings = get_settings()
    engines: dict = {}
    sora = Sora2SceneClient(settings)
    if sora.configured():
        engines["sora2"] = sora
    # Kling reference engine (real-face capable) registers when fal is configured.
    try:
        from backend.services.scene.kling_client import KlingSceneClient

        kling = KlingSceneClient(settings)
        if kling.configured():
            engines["kling"] = kling
    except Exception as exc:  # noqa: BLE001 — optional engine
        logger.warning("kling_engine_unavailable", error=str(exc)[:200])
    default = "sora2" if "sora2" in engines else (next(iter(engines), "sora2"))
    return SceneService(engines=engines, default_engine=default)
