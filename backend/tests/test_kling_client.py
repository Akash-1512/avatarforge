"""Kling image-to-video client: reference-frame -> video via fal (mocked)."""

import httpx
import pytest

from backend.config import get_settings
from backend.services.scene.kling_client import KlingSceneClient, _snap_duration
from backend.services.scene.sora2_client import SceneEngineError


def _client(monkeypatch, key="k"):
    s = get_settings()
    monkeypatch.setattr(s, "fal_api_key", key, raising=False)
    return KlingSceneClient(s)


def test_accepts_real_face():
    assert KlingSceneClient.accepts_real_face is True


def test_snap_duration():
    assert _snap_duration(4) == 5
    assert _snap_duration(8) == 10
    assert _snap_duration(5) == 5


@pytest.mark.asyncio
async def test_not_configured(monkeypatch):
    with pytest.raises(SceneEngineError) as ei:
        await _client(monkeypatch, key="").generate("x", reference_image=b"img")
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_requires_reference_image(monkeypatch):
    with pytest.raises(SceneEngineError) as ei:
        await _client(monkeypatch).generate("x", reference_image=None)
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_generate_direct_result(monkeypatch):
    c = _client(monkeypatch)
    captured = {}

    def handler(request):
        url = str(request.url)
        if "kling-video" in url and request.method == "POST":
            import json as _j

            body = _j.loads(request.content)
            captured["has_start_image"] = body["start_image_url"].startswith("data:image")
            captured["duration"] = body["duration"]
            return httpx.Response(200, json={"video": {"url": "https://f/clip.mp4"}})
        if url == "https://f/clip.mp4":
            return httpx.Response(200, content=b"KLINGMP4")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: orig(
            *a, transport=transport, **{x: y for x, y in k.items() if x != "transport"}
        ),
    )
    out = await c.generate("a person waves", seconds=4, reference_image=b"\xff\xd8facebytes")
    assert out == b"KLINGMP4"
    assert captured["has_start_image"] is True  # the reference frame was sent
    assert captured["duration"] == "5"  # snapped from 4
