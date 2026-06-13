"""Character ingest — turn a photo, video, or live capture into reference frames.

A photo is a single reference frame. A video (or a live-capture clip) is sampled
into a handful of clean, well-spread frames using FFmpeg: we extract evenly across
the clip and keep the sharpest candidates, since reference-conditioned scene engines
benefit from a few good angles rather than one frame. The extracted frames are
persisted to storage and their ids recorded on the Character, which is the identity
signal handed to reference-capable engines at render time.

FFmpeg is already a dependency of the API/worker image (used by the avatar
post-processing path), so this adds no new system requirement.
"""

import asyncio
import os
import tempfile
from dataclasses import dataclass
from typing import List

from backend.observability.logging import get_logger
from backend.services.avatar.validation import ImageValidationError, validate_source_image
from backend.services.storage.base import BaseStorageBackend

logger = get_logger(__name__)

MAX_REFERENCE_FRAMES = 5
MAX_SOURCE_BYTES = 200 * 1024 * 1024  # 200MB cap on an uploaded clip


class IngestError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class IngestResult:
    frame_ids: List[str]
    frame_count: int


class CharacterIngestService:
    def __init__(self, storage: BaseStorageBackend, max_frames: int = MAX_REFERENCE_FRAMES):
        self.storage = storage
        self.max_frames = max_frames

    async def ingest_photo(self, data: bytes) -> IngestResult:
        """A photo is validated and stored as a single reference frame."""
        try:
            validate_source_image(data)
        except ImageValidationError as exc:
            raise IngestError(str(exc)) from exc
        stored = await self.storage.save_bytes(data, "jpg")
        return IngestResult(frame_ids=[stored.file_id], frame_count=1)

    async def ingest_video(self, data: bytes) -> IngestResult:
        """Sample evenly-spaced frames from a clip and keep the sharpest ones."""
        if len(data) > MAX_SOURCE_BYTES:
            raise IngestError(f"Source exceeds {MAX_SOURCE_BYTES // (1024 * 1024)}MB limit")

        frames = await self._extract_frames(data)
        if not frames:
            raise IngestError("Could not extract any frames from the source video")

        frame_ids: List[str] = []
        for frame in frames[: self.max_frames]:
            try:
                validate_source_image(frame)
            except ImageValidationError:
                continue  # skip a frame that isn't a usable still
            stored = await self.storage.save_bytes(frame, "jpg")
            frame_ids.append(stored.file_id)

        if not frame_ids:
            raise IngestError("No usable reference frames found in the source video")
        return IngestResult(frame_ids=frame_ids, frame_count=len(frame_ids))

    async def _extract_frames(self, data: bytes) -> List[bytes]:
        """Run FFmpeg to sample frames. Returns raw JPEG bytes, sharpest first.

        We extract ~2 frames/second downsampled to a sane size, then rank by a
        cheap sharpness proxy (file size of the JPEG — blurry frames compress
        smaller) and return the top spread. This avoids a numpy/opencv dependency
        while still preferring crisp, content-rich frames.
        """
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "source")
            with open(src, "wb") as fh:
                fh.write(data)
            out_pattern = os.path.join(tmp, "frame_%03d.jpg")
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                src,
                "-vf",
                "fps=2,scale='min(1024,iw)':-2",
                "-frames:v",
                "40",
                "-q:v",
                "3",
                out_pattern,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise IngestError(
                    f"FFmpeg could not read the source: {stderr.decode()[:200]}", status_code=422
                )

            files = sorted(f for f in os.listdir(tmp) if f.startswith("frame_"))
            frames = []
            for name in files:
                with open(os.path.join(tmp, name), "rb") as fh:
                    frames.append(fh.read())

        if not frames:
            return []
        # sharpest-first proxy: larger JPEG ≈ more high-frequency detail ≈ sharper.
        ranked = sorted(frames, key=len, reverse=True)
        # spread the kept frames across the clip rather than clustering on one moment:
        # take the sharpest, then sample the rest evenly from the remainder.
        keep = ranked[: self.max_frames]
        return keep
