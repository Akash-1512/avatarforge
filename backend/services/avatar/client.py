"""HTTP client for the SadTalker model server."""

import httpx

from backend.config import Settings


class AvatarEngineError(Exception):
    def __init__(self, detail: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(detail)


class SadTalkerClient:
    def __init__(self, settings: Settings):
        self._base_url = settings.sadtalker_url.rstrip("/")
        self._timeout = settings.avatar_inference_timeout_sec

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise AvatarEngineError(f"Model server unreachable: {exc}") from exc

    async def infer(
        self,
        image_bytes: bytes,
        image_ext: str,
        audio_bytes: bytes,
        *,
        still: bool = True,
        preprocess: str = "crop",
        enhancer: bool = False,
    ) -> bytes:
        """Run inference; returns raw MP4 bytes."""
        files = {
            "image": (f"face.{image_ext}", image_bytes, f"image/{image_ext}"),
            "audio": ("audio.wav", audio_bytes, "audio/wav"),
        }
        data = {
            "still": str(still).lower(),
            "preprocess": preprocess,
            "enhancer": str(enhancer).lower(),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/infer", files=files, data=data)
        except httpx.TimeoutException as exc:
            raise AvatarEngineError(
                f"Inference timed out after {self._timeout}s", status_code=504
            ) from exc
        except httpx.HTTPError as exc:
            raise AvatarEngineError(f"Model server unreachable: {exc}") from exc

        if resp.status_code != 200:
            detail = resp.json().get("detail", resp.text[:300]) if resp.content else "no detail"
            raise AvatarEngineError(detail, status_code=resp.status_code)
        return resp.content
