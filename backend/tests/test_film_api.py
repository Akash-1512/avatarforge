"""Film API: /director/storyboard and /film/compose end-to-end (mocked engine/LLM)."""

import subprocess

import pytest
from fastapi.testclient import TestClient

import backend.api.v1.film as film_api
from backend.main import create_app
from backend.services.composition.service import CompositionService
from backend.services.director.service import DirectorService
from backend.services.scene.service import SceneService


def _clip():
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
                "testsrc=duration=1:size=320x240:rate=10",
                "-pix_fmt",
                "yuv420p",
                out,
            ],
            check=True,
        )
        return open(out, "rb").read()


class _FakeLLM:
    async def complete_json_raw(self, system, user):
        return (
            '{"title":"Fox Tale","style":"anime","scenes":['
            '{"shot":"a fox wakes","camera":"push-in","dialogue":"","seconds":3},'
            '{"shot":"a fox runs","camera":"tracking","dialogue":"","seconds":3}]}'
        )


class _FakeEngine:
    name = "sora2"
    accepts_real_face = False

    async def generate(self, prompt, seconds=5, size="1280x720"):
        return _clip()


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    monkeypatch.setattr(film_api, "get_director_service", lambda: DirectorService(_FakeLLM()))
    scenes = SceneService(engines={"sora2": _FakeEngine()}, default_engine="sora2")
    monkeypatch.setattr(film_api, "get_composition_service", lambda: CompositionService(scenes))


def test_storyboard_endpoint():
    client = TestClient(create_app())
    r = client.post("/api/v1/director/storyboard", json={"brief": "a short film about a fox"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene_count"] == 2 and body["total_seconds"] == 6
    assert body["storyboard"]["style"] == "anime"


def test_compose_endpoint_renders_and_stitches():
    client = TestClient(create_app())
    sb = client.post("/api/v1/director/storyboard", json={"brief": "fox"}).json()["storyboard"]
    r = client.post("/api/v1/film/compose", json={"storyboard": sb})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene_count"] == 2 and body["clip_id"]
    assert [s["engine"] for s in body["scenes"]] == ["sora2", "sora2"]
