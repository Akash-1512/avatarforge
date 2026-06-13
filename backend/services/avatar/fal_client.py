"""fal.ai avatar engine — managed HunyuanVideo-Avatar behind the same interface.

This is the third engine in the registry, and the most instructive one: it
proves the contract holds across deployment models, not just across models.
SadTalker and the self-hosted Hunyuan server speak our local /infer HTTP
contract; fal speaks its own queue API. Yet from AvatarService's side this
client is identical — same `infer(image_bytes, image_ext, audio_bytes) -> bytes`
and `health() -> dict`. The adapter absorbs the difference.

fal's flow (raw REST, no SDK dependency — keeps our stack consistent):
  1. upload image + audio to fal storage   -> URLs
  2. POST queue.fal.run/{model}            -> request_id + status/response URLs
  3. poll status until COMPLETED            (the model takes ~8 min)
  4. GET the response, download video.url   -> raw MP4 bytes

Auth: `Authorization: Key <FAL_KEY>`. Pricing as of build: $1.40 / 5s clip,
billed only on success.
"""

import asyncio
import base64
import time

import httpx

from backend.config import Settings
from backend.services.avatar.client import AvatarEngineError

_FAL_QUEUE = "https://queue.fal.run"
_MODEL = "fal-ai/hunyuan-avatar"
_POLL_INTERVAL_SEC = 5.0
_TERMINAL_OK = "COMPLETED"


class FalAvatarClient:
    """Adapter for fal-ai/hunyuan-avatar. Duck-types SadTalkerClient."""

    def __init__(self, settings: Settings, api_key: str | None = None):
        self._key = api_key or settings.fal_api_key
        self._timeout = settings.avatar_inference_timeout_sec
        self._model = settings.fal_avatar_model or _MODEL

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Key {self._key}"}

    async def health(self) -> dict:
        """No ping endpoint on fal; report readiness from config presence."""
        return {
            "status": "ok" if self._key else "degraded",
            "engine": "fal",
            "model": self._model,
            "api_key_present": bool(self._key),
        }

    @staticmethod
    def _data_uri(data: bytes, content_type: str) -> str:
        """Inline bytes as a base64 data URI.

        fal accepts data URIs anywhere a file URL is expected and decodes them
        server-side. For a photo plus a few seconds of audio this stays within
        sane request limits and removes the whole upload round-trip (and its
        failure modes) — simpler and more reliable than fal storage for our
        payload sizes.
        """
        return f"data:{content_type};base64,{base64.b64encode(data).decode()}"

    async def infer(
        self,
        image_bytes: bytes,
        image_ext: str,
        audio_bytes: bytes,
        *,
        still: bool = True,  # accepted for contract parity; not used by fal
        preprocess: str = "crop",  # ditto
        enhancer: bool = False,  # ditto
        text: str = "A person speaking directly to the camera.",
    ) -> bytes:
        if not self._key:
            raise AvatarEngineError("FAL_API_KEY not configured", status_code=503)

        started = time.monotonic()
        try:
            image_url = self._data_uri(image_bytes, f"image/{image_ext}")
            audio_url = self._data_uri(audio_bytes, "audio/wav")

            async with httpx.AsyncClient(timeout=30.0) as client:
                submit = await client.post(
                    f"{_FAL_QUEUE}/{self._model}",
                    headers={**self._auth, "Content-Type": "application/json"},
                    json={"image_url": image_url, "audio_url": audio_url, "text": text},
                )
                if submit.status_code not in (200, 202):
                    raise AvatarEngineError(
                        f"fal submit failed: {submit.status_code} {submit.text[:200]}",
                        status_code=502,
                    )
                body = submit.json()
                status_url = body["status_url"]
                response_url = body["response_url"]

            # Poll on a fresh short-timeout client; the long wait is many small calls,
            # not one blocked socket (so no 100s-proxy-class problem, and cancellable).
            video_url = await self._poll_until_done(status_url, response_url, started)

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                dl = await client.get(video_url)
            if dl.status_code != 200:
                raise AvatarEngineError(
                    f"fal video download failed: {dl.status_code}", status_code=502
                )
            return dl.content

        except httpx.TimeoutException as exc:
            raise AvatarEngineError(f"fal request timed out: {exc}", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AvatarEngineError(f"fal unreachable: {exc}", status_code=502) from exc

    async def _poll_until_done(self, status_url: str, response_url: str, started: float) -> str:
        while True:
            if time.monotonic() - started > self._timeout:
                raise AvatarEngineError(
                    f"fal generation exceeded {self._timeout}s", status_code=504
                )
            async with httpx.AsyncClient(timeout=15.0) as client:
                st = await client.get(status_url, headers=self._auth)
                # fal returns 202 while IN_QUEUE/IN_PROGRESS and 200 when ready.
                # Both are valid; only other codes are real failures. The
                # authoritative state is the `status` field in the body.
                if st.status_code not in (200, 202):
                    raise AvatarEngineError(
                        f"fal status check failed: {st.status_code}", status_code=502
                    )
                status = st.json().get("status")
                if status == _TERMINAL_OK:
                    res = await client.get(response_url, headers=self._auth)
                    if res.status_code != 200:
                        raise AvatarEngineError(
                            f"fal result fetch failed: {res.status_code}", status_code=502
                        )
                    payload = res.json()
                    video = payload.get("video") or {}
                    url = video.get("url")
                    if not url:
                        raise AvatarEngineError(
                            f"fal completed without a video URL: {str(payload)[:200]}",
                            status_code=502,
                        )
                    return url
                if status in ("FAILED", "ERROR"):
                    raise AvatarEngineError(
                        f"fal generation failed: {str(st.json())[:200]}", status_code=502
                    )
            await asyncio.sleep(_POLL_INTERVAL_SEC)
