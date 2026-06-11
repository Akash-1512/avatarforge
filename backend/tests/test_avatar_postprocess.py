"""MP4 packaging — real ffmpeg on a generated test video."""

import subprocess

import pytest

from backend.services.avatar.postprocess import VideoProcessingError, package_mp4, probe_video


def _test_video(width=320, height=240, dur=1) -> bytes:
    """Generate a tiny test-pattern MP4 (mpeg4 codec, deliberately not h264)."""
    return subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={dur}:size={width}x{height}:rate=10",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={dur}",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            "-f",
            "mp4",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout


@pytest.mark.asyncio
async def test_packages_to_h264():
    packaged = await package_mp4(_test_video())
    meta = await probe_video(packaged)
    assert meta["codec"] == "h264"
    assert meta["duration_sec"] >= 0.9


@pytest.mark.asyncio
async def test_caps_height_at_720():
    packaged = await package_mp4(_test_video(width=1920, height=1440))
    meta = await probe_video(packaged)
    assert meta["height"] <= 720


@pytest.mark.asyncio
async def test_small_video_not_upscaled():
    packaged = await package_mp4(_test_video(width=320, height=240))
    meta = await probe_video(packaged)
    assert meta["height"] == 240


@pytest.mark.asyncio
async def test_garbage_raises():
    with pytest.raises(VideoProcessingError):
        await package_mp4(b"not a video at all")
