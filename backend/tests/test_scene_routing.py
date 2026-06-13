"""Scene engine routing — content policy decides the engine, not just price."""

import pytest

from backend.services.scene.service import SceneRequest, SceneService
from backend.services.scene.sora2_client import SceneEngineError


class _FakeEngine:
    def __init__(self, name, accepts_real_face):
        self.name = name
        self.accepts_real_face = accepts_real_face
        self.calls = 0

    async def generate(self, prompt, seconds=5, size="1280x720"):
        self.calls += 1
        return b"MP4"


def _svc(real_face_capable=True):
    engines = {"sora2": _FakeEngine("sora2", accepts_real_face=False)}
    if real_face_capable:
        engines["kling"] = _FakeEngine("kling", accepts_real_face=True)
    return SceneService(engines=engines, default_engine="sora2")


def test_text_scene_routes_to_default_sora():
    svc = _svc()
    assert svc.route(SceneRequest(prompt="a city at dawn")) == "sora2"


def test_real_face_routes_to_reference_capable_engine():
    svc = _svc()
    # a real-person reference must NOT go to sora2 (which rejects faces)
    name = svc.route(SceneRequest(prompt="hero walks", has_real_face_reference=True))
    assert name == "kling"


def test_real_face_with_no_capable_engine_raises_503():
    svc = _svc(real_face_capable=False)
    with pytest.raises(SceneEngineError) as ei:
        svc.route(SceneRequest(prompt="hero", has_real_face_reference=True))
    assert ei.value.status_code == 503


def test_explicit_engine_override_wins():
    svc = _svc()
    assert svc.route(SceneRequest(prompt="x", engine="kling")) == "kling"


def test_unconfigured_engine_resolves_to_503():
    svc = _svc()
    with pytest.raises(SceneEngineError) as ei:
        svc.resolve("nonexistent")
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_generate_invokes_routed_engine():
    svc = _svc()
    out = await svc.generate(SceneRequest(prompt="a quiet forest"))
    assert out == b"MP4"
    assert svc.engines["sora2"].calls == 1
    assert svc.engines["kling"].calls == 0


def test_available_reports_real_face_capable():
    info = _svc().available()
    assert "kling" in info["real_face_capable"]
    assert "sora2" not in info["real_face_capable"]
