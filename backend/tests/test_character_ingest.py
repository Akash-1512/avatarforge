"""Character ingest: photo single-frame, video FFmpeg sampling, validation."""

import subprocess

import pytest

from backend.services.character.ingest import CharacterIngestService, IngestError


class _MemStorage:
    """Minimal in-memory storage backend for tests."""

    def __init__(self):
        self.saved = {}

    async def save_bytes(self, data, extension):
        from backend.services.storage.base import StoredFile

        fid = f"f{len(self.saved)}.{extension}"
        self.saved[fid] = data
        return StoredFile(
            file_id=fid, path=f"/tmp/{fid}", url=f"/media/{fid}", size_bytes=len(data)
        )

    def resolve_path(self, file_id):
        return f"/tmp/{file_id}" if file_id in self.saved else None


def _png_bytes(size=512):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (size, size), (120, 90, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _tiny_mp4():
    """Generate a 2s test video with FFmpeg (testsrc), returned as bytes."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "t.mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=2:size=640x480:rate=10",
                "-pix_fmt",
                "yuv420p",
                out,
            ],
            check=True,
        )
        with open(out, "rb") as fh:
            return fh.read()


@pytest.mark.asyncio
async def test_photo_ingest_one_frame():
    svc = CharacterIngestService(_MemStorage())
    res = await svc.ingest_photo(_png_bytes())
    assert res.frame_count == 1 and len(res.frame_ids) == 1


@pytest.mark.asyncio
async def test_photo_ingest_rejects_garbage():
    svc = CharacterIngestService(_MemStorage())
    with pytest.raises(IngestError):
        await svc.ingest_photo(b"not an image")


@pytest.mark.asyncio
async def test_video_ingest_samples_multiple_frames():
    svc = CharacterIngestService(_MemStorage(), max_frames=5)
    res = await svc.ingest_video(_tiny_mp4())
    assert 1 <= res.frame_count <= 5
    assert len(res.frame_ids) == res.frame_count


@pytest.mark.asyncio
async def test_video_ingest_rejects_oversize():
    svc = CharacterIngestService(_MemStorage())
    with pytest.raises(IngestError):
        await svc.ingest_video(b"x" * (201 * 1024 * 1024))
