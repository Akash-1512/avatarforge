"""Azure Sora 2 scene engine — text-to-scene video on Azure AI Foundry.

Verified against Microsoft Learn (preview, June 2026):
- Create:   POST {endpoint}/openai/v1/videos?api-version=preview
            body: {model, prompt, seconds (str), size (e.g. "1280x720")}
- Status:   GET  {endpoint}/openai/v1/videos/{video_id}?api-version=preview
            status transitions: queued -> in_progress -> completed | failed
- Download: GET  the completed video's content endpoint -> MP4 bytes
- Auth:     "api-key" header (key) — keyless Entra ID is also supported.

Content policy (enforced server-side, designed around in the registry):
real people including public figures cannot be generated, and input images with
human faces are rejected. So this engine serves text-to-scene and non-real-face
stylized content; real-person reference shots are routed elsewhere by the registry.
"""

import asyncio
import time

import httpx

from backend.config import Settings
from backend.observability.logging import get_logger

logger = get_logger(__name__)

_API_VERSION = "preview"
_TERMINAL_OK = "completed"
_TERMINAL_FAIL = "failed"


class SceneEngineError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class Sora2SceneClient:
    """Text-to-scene engine. Does not accept real human faces by policy."""

    name = "sora2"
    accepts_real_face = False  # registry routing signal

    def __init__(self, settings: Settings):
        self._endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
        self._api_key = settings.azure_openai_api_key
        self._deployment = getattr(settings, "azure_sora_deployment", "sora-2") or "sora-2"
        self._timeout = settings.avatar_inference_timeout_sec

    def configured(self) -> bool:
        return bool(self._endpoint and self._api_key)

    async def health(self) -> dict:
        return {"engine": self.name, "configured": self.configured()}

    def _headers(self) -> dict:
        return {"api-key": self._api_key, "Content-Type": "application/json"}

    async def generate(self, prompt: str, seconds: int = 5, size: str = "1280x720") -> bytes:
        """Create a Sora 2 render job, poll to completion, return MP4 bytes."""
        if not self.configured():
            raise SceneEngineError("Azure Sora 2 not configured", status_code=503)

        create_url = f"{self._endpoint}/openai/v1/videos?api-version={_API_VERSION}"
        body = {
            "model": self._deployment,
            "prompt": prompt,
            "seconds": str(seconds),
            "size": size,
        }
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=60) as http:
            try:
                resp = await http.post(create_url, headers=self._headers(), json=body)
            except httpx.HTTPError as exc:
                raise SceneEngineError(f"Sora 2 unreachable: {exc}", status_code=502) from exc
            if resp.status_code >= 400:
                raise SceneEngineError(
                    f"Sora 2 create failed: {resp.status_code} {resp.text[:200]}",
                    status_code=resp.status_code,
                )
            video_id = resp.json().get("id")
            if not video_id:
                raise SceneEngineError("Sora 2 create returned no video id")

        await self._poll(video_id, started)
        return await self._download(video_id)

    async def _poll(self, video_id: str, started: float) -> None:
        status_url = f"{self._endpoint}/openai/v1/videos/{video_id}?api-version={_API_VERSION}"
        async with httpx.AsyncClient(timeout=30) as http:
            while True:
                if time.monotonic() - started > self._timeout:
                    raise SceneEngineError("Sora 2 render timed out", status_code=504)
                resp = await http.get(status_url, headers=self._headers())
                if resp.status_code >= 400:
                    raise SceneEngineError(
                        f"Sora 2 status failed: {resp.status_code} {resp.text[:200]}",
                        status_code=resp.status_code,
                    )
                status = (resp.json() or {}).get("status")
                if status == _TERMINAL_OK:
                    return
                if status == _TERMINAL_FAIL:
                    raise SceneEngineError("Sora 2 reported the render failed")
                await asyncio.sleep(5)

    async def _download(self, video_id: str) -> bytes:
        url = f"{self._endpoint}/openai/v1/videos/{video_id}/content" f"?api-version={_API_VERSION}"
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.get(url, headers={"api-key": self._api_key})
            if resp.status_code >= 400:
                raise SceneEngineError(
                    f"Sora 2 download failed: {resp.status_code}", status_code=resp.status_code
                )
            return resp.content
