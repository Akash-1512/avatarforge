"""Lip-sync engine — make a character speak, via VEED Fabric on fal.

Takes a character image (a reference or a restyled still) plus an audio track and
returns a short talking video with mouth motion synced to the audio. This is the
"character speaks the dialogue" step of the film pipeline.

Verified (fal, June 2026): veed/fabric-1.0 takes image_url + audio_url, resolution
"480p" ($0.08/s) or "720p" ($0.15/s), ~30s per clip. Same fal submit/poll/result
mechanics the avatar and style engines already use.
"""

import asyncio
import base64
import time
from functools import lru_cache
from typing import Optional

import httpx

from backend.config import Settings, get_settings
from backend.observability.logging import get_logger

logger = get_logger(__name__)

_SUBMIT_URL = "https://queue.fal.run/veed/fabric-1.0"


class LipSyncError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class LipSyncService:
    name = "veed_fabric"

    def __init__(self, settings: Settings, api_key: Optional[str] = None):
        self._key = api_key or settings.fal_api_key
        self._timeout = settings.avatar_inference_timeout_sec

    def configured(self) -> bool:
        return bool(self._key)

    @staticmethod
    def _data_uri(data: bytes, content_type: str) -> str:
        return f"data:{content_type};base64,{base64.b64encode(data).decode()}"

    async def sync(self, image_bytes: bytes, audio_bytes: bytes, resolution: str = "720p") -> bytes:
        if not self.configured():
            raise LipSyncError("Lip-sync not configured: FAL_API_KEY missing", 503)
        if resolution not in ("480p", "720p"):
            raise LipSyncError(f"resolution must be 480p or 720p, got {resolution}", 422)

        payload = {
            "image_url": self._data_uri(image_bytes, "image/jpeg"),
            "audio_url": self._data_uri(audio_bytes, "audio/wav"),
            "resolution": resolution,
        }
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=60) as http:
            try:
                resp = await http.post(
                    _SUBMIT_URL, headers={"Authorization": f"Key {self._key}"}, json=payload
                )
            except httpx.HTTPError as exc:
                raise LipSyncError(f"fal unreachable: {exc}", 502) from exc
            if resp.status_code >= 400:
                raise LipSyncError(
                    f"Lip-sync submit failed: {resp.status_code} {resp.text[:200]}",
                    resp.status_code,
                )
            body = resp.json()
            url = self._extract_video_url(body) or await self._poll(body, started)

        async with httpx.AsyncClient(timeout=120) as http:
            vid = await http.get(url)
            if vid.status_code >= 400:
                raise LipSyncError(f"Lip-sync video fetch failed: {vid.status_code}")
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
            raise LipSyncError("Lip-sync returned no result and no queue handle")
        async with httpx.AsyncClient(timeout=30) as http:
            while True:
                if time.monotonic() - started > self._timeout:
                    raise LipSyncError("Lip-sync timed out", 504)
                st = await http.get(status_url, headers={"Authorization": f"Key {self._key}"})
                status = (st.json() or {}).get("status")
                if status == "COMPLETED" or st.status_code == 200:
                    res = await http.get(
                        response_url, headers={"Authorization": f"Key {self._key}"}
                    )
                    url = self._extract_video_url(res.json())
                    if url is None:
                        raise LipSyncError("Lip-sync result had no video url")
                    return url
                await asyncio.sleep(3)


@lru_cache
def get_lipsync_service() -> LipSyncService:
    return LipSyncService(get_settings())
