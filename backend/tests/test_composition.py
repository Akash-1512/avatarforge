"""Composition: fan out scenes over the routed engine + FFmpeg stitch."""

import subprocess

import pytest

from backend.services.composition.service import CompositionError, CompositionService, scene_prompt
from backend.services.director.service import Scene, Storyboard
from backend.services.scene.service import SceneService


def _clip(seconds=1):
    """A real tiny MP4 so the FFmpeg concat path is genuinely exercised."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "c.mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=duration={seconds}:size=320x240:rate=10",
                "-pix_fmt",
                "yuv420p",
                out,
            ],
            check=True,
        )
        with open(out, "rb") as fh:
            return fh.read()


class _FakeEngine:
    name = "sora2"
    accepts_real_face = False

    def __init__(self):
        self.calls = 0

    async def generate(self, prompt, seconds=5, size="1280x720"):
        self.calls += 1
        return _clip(1)


def _board(n=3):
    return Storyboard(
        title="T",
        style="anime",
        scenes=[Scene(shot=f"s{i}", camera="static", dialogue="", seconds=3) for i in range(n)],
    )


def test_scene_prompt_includes_style_and_camera():
    p = scene_prompt("a fox runs", "tracking left", "pixar")
    assert "a fox runs" in p and "tracking left" in p and "pixar style" in p


def test_scene_prompt_realistic_has_no_style_phrase():
    assert "style" not in scene_prompt("a fox", "wide", "realistic")


@pytest.mark.asyncio
async def test_render_fans_out_and_stitches():
    eng = _FakeEngine()
    svc = CompositionService(SceneService(engines={"sora2": eng}, default_engine="sora2"))
    result = await svc.render(_board(3))
    assert eng.calls == 3  # one render per scene
    assert len(result.clips) == 3
    assert result.total_seconds == 9
    assert result.stitched[:4] != b""  # produced a stitched mp4
    assert len(result.stitched) > 0


@pytest.mark.asyncio
async def test_single_scene_skips_stitch():
    eng = _FakeEngine()
    svc = CompositionService(SceneService(engines={"sora2": eng}, default_engine="sora2"))
    result = await svc.render(_board(1))
    assert len(result.clips) == 1 and eng.calls == 1


@pytest.mark.asyncio
async def test_empty_storyboard_rejected():
    svc = CompositionService(SceneService(engines={"sora2": _FakeEngine()}))
    with pytest.raises(CompositionError):
        await svc.render(Storyboard(title="x", style="anime", scenes=[]))
