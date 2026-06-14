"""Kling scene engine — reference-capable image-to-video on fal.

The complement to Sora 2: Kling accepts a real human-face reference (the character's
stored frame) as the start image and animates it with identity preserved, so it serves
the real-person route Azure Sora 2 rejects by policy. It speaks fal's queue protocol —
the same submit/poll/result pattern the avatar FalAvatarClient uses.

Verified (fal, June 2026): fal-ai/kling-video/v2.6/pro/image-to-video takes
`start_image_url` + `prompt` (+ optional `duration`, `generate_audio`), returns
`video.url`. The start image may be a base64 data URI; aspect ratio is inferred
from it.
"""

import asyncio
import base64
import time
from typing import Optional

import httpx

from backend.config import Settings
from backend.observability.logging import get_logger
from backend.services.scene.sora2_client import SceneEngineError

logger = get_logger(__name__)

_SUBMIT_URL = "https://queue.fal.run/fal-ai/kling-video/v2.6/pro/image-to-video"
_KLING_DURATIONS = (5, 10)


def _snap_duration(seconds: int) -> int:
    return min(_KLING_DURATIONS, key=lambda v: (abs(v - seconds), v))


class KlingSceneClient:
    """Reference-capable scene engine (accepts real faces) on fal."""

    name = "kling"
    accepts_real_face = True  # registry routing signal

    def __init__(self, settings: Settings, api_key: Optional[str] = None):
        self._key = api_key or settings.fal_api_key
        self._timeout = settings.avatar_inference_timeout_sec

    def configured(self) -> bool:
        return bool(self._key)

    async def health(self) -> dict:
        return {"engine": self.name, "configured": self.configured(), "accepts_real_face": True}

    @staticmethod
    def _data_uri(data: bytes, content_type: str = "image/jpeg") -> str:
        return f"data:{content_type};base64,{base64.b64encode(data).decode()}"

    async def generate(
        self,
        prompt: str,
        seconds: int = 5,
        size: str = "1280x720",
        reference_image: Optional[bytes] = None,
    ) -> bytes:
        if not self.configured():
            raise SceneEngineError("Kling (fal) not configured: FAL_API_KEY missing", 503)
        if reference_image is None:
            raise SceneEngineError(
                "Kling requires a reference image (a character frame)", status_code=422
            )

        payload = {
            "prompt": prompt,
            "start_image_url": self._data_uri(reference_image),
            "duration": str(_snap_duration(seconds)),
            "generate_audio": False,  # voice + lip-sync is layered separately
        }
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=60) as http:
            try:
                resp = await http.post(
                    _SUBMIT_URL, headers={"Authorization": f"Key {self._key}"}, json=payload
                )
            except httpx.HTTPError as exc:
                raise SceneEngineError(f"Kling unreachable: {exc}", 502) from exc
            if resp.status_code >= 400:
                raise SceneEngineError(
                    f"Kling submit failed: {resp.status_code} {resp.text[:200]}", resp.status_code
                )
            body = resp.json()
            url = self._extract_video_url(body) or await self._poll(body, started)

        async with httpx.AsyncClient(timeout=180) as http:
            vid = await http.get(url)
            if vid.status_code >= 400:
                raise SceneEngineError(f"Kling video fetch failed: {vid.status_code}")
            return vid.content

    @staticmethod
    def _extract_video_url(body: dict) -> Optional[str]:
        video = (body or {}).get("video")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        return None

    async def _poll(self, submit_body: dict, started: float) -> str:
        status_url = submit_body.get("status_url")
        response_url = submit_body.get("response_url")
        if not status_url or not response_url:
            raise SceneEngineError("Kling returned no result and no queue handle")
        async with httpx.AsyncClient(timeout=30) as http:
            while True:
                if time.monotonic() - started > self._timeout:
                    raise SceneEngineError("Kling render timed out", 504)
                st = await http.get(status_url, headers={"Authorization": f"Key {self._key}"})
                status = (st.json() or {}).get("status")
                if status == "COMPLETED" or st.status_code == 200:
                    res = await http.get(
                        response_url, headers={"Authorization": f"Key {self._key}"}
                    )
                    url = self._extract_video_url(res.json())
                    if url is None:
                        raise SceneEngineError("Kling result had no video url")
                    return url
                await asyncio.sleep(5)
