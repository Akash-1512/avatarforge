"""Sora 2 client — verified Azure /openai/v1/videos preview flow, mocked HTTP."""

import httpx
import pytest

from backend.config import get_settings
from backend.services.scene.sora2_client import SceneEngineError, Sora2SceneClient


def _client(monkeypatch, endpoint="https://r.openai.azure.com", key="k"):
    s = get_settings()
    monkeypatch.setattr(s, "azure_openai_endpoint", endpoint, raising=False)
    monkeypatch.setattr(s, "azure_openai_api_key", key, raising=False)
    return Sora2SceneClient(s)


def test_not_configured_without_endpoint(monkeypatch):
    c = _client(monkeypatch, endpoint="", key="")
    assert c.configured() is False


def test_does_not_accept_real_faces():
    # the policy signal the registry routes on
    assert Sora2SceneClient.accepts_real_face is False


@pytest.mark.asyncio
async def test_generate_happy_path(monkeypatch):
    c = _client(monkeypatch)
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.endswith("videos?api-version=preview"):
            return httpx.Response(200, json={"id": "vid_1"})
        if "/videos/vid_1/content" in url:
            return httpx.Response(200, content=b"MP4BYTES")
        if "/videos/vid_1" in url:
            state["polls"] += 1
            status = "completed" if state["polls"] >= 1 else "in_progress"
            return httpx.Response(200, json={"status": status})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient

    def patched(*a, **k):
        k["transport"] = transport
        return orig(*a, **k)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    out = await c.generate("a serene lake at sunset", seconds=5)
    assert out == b"MP4BYTES"


@pytest.mark.asyncio
async def test_generate_raises_on_failed_status(monkeypatch):
    c = _client(monkeypatch)

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"id": "vid_x"})
        return httpx.Response(200, json={"status": "failed"})

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: orig(
            *a, transport=transport, **{x: y for x, y in k.items() if x != "transport"}
        ),
    )
    with pytest.raises(SceneEngineError):
        await c.generate("x", seconds=3)


def test_snap_seconds_to_allowed_set():
    from backend.services.scene.sora2_client import SORA2_ALLOWED_SECONDS, snap_seconds

    assert snap_seconds(5) == 4  # the value that triggered the live 400
    assert snap_seconds(1) == 4
    assert snap_seconds(7) == 8
    assert snap_seconds(10) == 8  # ties resolve to the smaller/closer
    assert snap_seconds(12) == 12
    assert snap_seconds(20) == 12
    for v in (4, 8, 12):
        assert v in SORA2_ALLOWED_SECONDS


@pytest.mark.asyncio
async def test_generate_snaps_invalid_seconds_before_request(monkeypatch):
    c = _client(monkeypatch)
    captured = {}

    def handler(request):
        import json as _j

        if request.method == "POST":
            captured["seconds"] = _j.loads(request.content)["seconds"]
            return httpx.Response(200, json={"id": "vid_s"})
        if "/content" in str(request.url):
            return httpx.Response(200, content=b"MP4")
        return httpx.Response(200, json={"status": "completed"})

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: orig(
            *a, transport=transport, **{x: y for x, y in k.items() if x != "transport"}
        ),
    )
    await c.generate("a forest", seconds=5)
    assert captured["seconds"] == "4"  # snapped, sent as string
