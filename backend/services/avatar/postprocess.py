"""Package raw inference output as delivery-ready H.264 MP4.

- H.264 + AAC for universal playback
- 720p height cap (SadTalker 256 output upscales cleanly)
- +faststart so browsers can stream without full download
"""

import asyncio
import json
import tempfile
from pathlib import Path


class VideoProcessingError(Exception):
    pass


async def package_mp4(raw_video: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        dst = Path(tmp) / "out.mp4"
        src.write_bytes(raw_video)

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-vf",
            "scale=-2:'min(720,ih)'",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            str(dst),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise VideoProcessingError(f"ffmpeg packaging failed: {stderr.decode()[-300:]}")
        return dst.read_bytes()


async def probe_video(video_bytes: bytes) -> dict:
    """Return codec/dimensions/duration via ffprobe."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "v.mp4"
        src.write_bytes(video_bytes)
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(src),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        info = json.loads(out)
        video_stream = next(
            (s for s in info.get("streams", []) if s.get("codec_type") == "video"), {}
        )
        return {
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "duration_sec": round(float(info.get("format", {}).get("duration", 0)), 2),
        }
