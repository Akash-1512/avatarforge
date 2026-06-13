"""Style engine — restyle a character reference into a chosen visual style.

Realistic is a pass-through (the reference is already realistic). Stylized targets
(anime, Pixar-3D, claymation, watercolor, ...) run the reference frame through
fal's FLUX LoRA image-to-image endpoint with a style prompt and a controlled
transformation strength: high enough to adopt the style, low enough to preserve
the person's structure/likeness. Each style is one registry entry — adding a new
look is a one-line addition, mirroring the engine-registry philosophy used for
scenes and avatars.

Verified (fal, June 2026): fal-ai/flux-lora/image-to-image, ~$0.035 per megapixel;
strength 0.0 preserves the original, 1.0 fully remakes it.
"""

import asyncio
import base64
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import httpx

from backend.config import Settings, get_settings
from backend.observability.logging import get_logger

logger = get_logger(__name__)

_SUBMIT_URL = "https://queue.fal.run/fal-ai/flux-lora/image-to-image"


@dataclass
class StyleSpec:
    """A style = a prompt + a transformation strength (+ optional LoRA url)."""

    prompt: str
    strength: float
    lora_url: Optional[str] = None


# realistic is intentionally absent: it is a pass-through (no restyle needed).
STYLE_REGISTRY: dict[str, StyleSpec] = {
    "anime": StyleSpec(
        "anime illustration, clean cel shading, expressive eyes, studio anime style",
        strength=0.62,
    ),
    "pixar": StyleSpec(
        "3D Pixar-style character, soft global illumination, rounded features, cinematic",
        strength=0.6,
    ),
    "3d": StyleSpec(
        "stylized 3D render, subsurface scattering, studio lighting, high detail",
        strength=0.58,
    ),
    "claymation": StyleSpec(
        "claymation stop-motion character, matte clay texture, handcrafted look",
        strength=0.66,
    ),
    "watercolor": StyleSpec(
        "watercolor portrait, soft washes, paper texture, painterly edges",
        strength=0.55,
    ),
}

SUPPORTED_STYLES = ["realistic", *STYLE_REGISTRY.keys()]


class StyleEngineError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class StyleService:
    def __init__(self, settings: Settings, api_key: Optional[str] = None):
        self._key = api_key or settings.fal_api_key
        self._timeout = settings.avatar_inference_timeout_sec

    def configured(self) -> bool:
        return bool(self._key)

    def supported(self) -> list[str]:
        return SUPPORTED_STYLES

    @staticmethod
    def _data_uri(data: bytes, content_type: str = "image/jpeg") -> str:
        return f"data:{content_type};base64,{base64.b64encode(data).decode()}"

    async def restyle(self, image_bytes: bytes, style: str) -> bytes:
        """Return restyled image bytes. Realistic is a no-op pass-through."""
        if style == "realistic":
            return image_bytes
        spec = STYLE_REGISTRY.get(style)
        if spec is None:
            raise StyleEngineError(f"Unknown style '{style}'. Supported: {SUPPORTED_STYLES}", 422)
        if not self.configured():
            raise StyleEngineError("Style engine not configured: FAL_API_KEY missing", 503)

        payload = {
            "image_url": self._data_uri(image_bytes),
            "prompt": spec.prompt,
            "strength": spec.strength,
        }
        if spec.lora_url:
            payload["loras"] = [{"path": spec.lora_url, "scale": 1.0}]

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=60) as http:
            try:
                resp = await http.post(
                    _SUBMIT_URL, headers={"Authorization": f"Key {self._key}"}, json=payload
                )
            except httpx.HTTPError as exc:
                raise StyleEngineError(f"fal unreachable: {exc}", 502) from exc
            if resp.status_code >= 400:
                raise StyleEngineError(
                    f"Style submit failed: {resp.status_code} {resp.text[:200]}", resp.status_code
                )
            body = resp.json()
            # fal sync-style endpoints may return the result directly, or a queue
            # handle to poll. Handle both.
            url = self._extract_image_url(body)
            if url is None:
                url = await self._poll(body, started)

        async with httpx.AsyncClient(timeout=60) as http:
            img = await http.get(url)
            if img.status_code >= 400:
                raise StyleEngineError(f"Style image fetch failed: {img.status_code}")
            return img.content

    @staticmethod
    def _extract_image_url(body: dict) -> Optional[str]:
        images = (body or {}).get("images")
        if images and isinstance(images, list) and images[0].get("url"):
            return images[0]["url"]
        return None

    async def _poll(self, submit_body: dict, started: float) -> str:
        status_url = submit_body.get("status_url")
        response_url = submit_body.get("response_url")
        if not status_url or not response_url:
            raise StyleEngineError("Style engine returned no result and no queue handle")
        async with httpx.AsyncClient(timeout=30) as http:
            while True:
                if time.monotonic() - started > self._timeout:
                    raise StyleEngineError("Style render timed out", 504)
                st = await http.get(status_url, headers={"Authorization": f"Key {self._key}"})
                status = (st.json() or {}).get("status")
                if status == "COMPLETED" or st.status_code == 200:
                    res = await http.get(
                        response_url, headers={"Authorization": f"Key {self._key}"}
                    )
                    url = self._extract_image_url(res.json())
                    if url is None:
                        raise StyleEngineError("Style result had no image url")
                    return url
                await asyncio.sleep(3)


@lru_cache
def get_style_service() -> StyleService:
    return StyleService(get_settings())
