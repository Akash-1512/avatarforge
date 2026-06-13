"""Lip-sync engine (VEED Fabric on fal), mocked HTTP."""

import httpx
import pytest

from backend.config import get_settings
from backend.services.scene.lipsync_client import LipSyncError, LipSyncService


def _svc(monkeypatch, key="k"):
    s = get_settings()
    monkeypatch.setattr(s, "fal_api_key", key, raising=False)
    return LipSyncService(s)


@pytest.mark.asyncio
async def test_not_configured(monkeypatch):
    with pytest.raises(LipSyncError) as ei:
        await _svc(monkeypatch, key="").sync(b"img", b"aud")
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_bad_resolution(monkeypatch):
    with pytest.raises(LipSyncError) as ei:
        await _svc(monkeypatch).sync(b"img", b"aud", resolution="4k")
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_sync_direct_result(monkeypatch):
    svc = _svc(monkeypatch)

    def handler(request):
        url = str(request.url)
        if "fabric-1.0" in url:
            return httpx.Response(200, json={"video": {"url": "https://f/talk.mp4"}})
        if url == "https://f/talk.mp4":
            return httpx.Response(200, content=b"TALKING")
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
    assert await svc.sync(b"IMG", b"AUD", "480p") == b"TALKING"
