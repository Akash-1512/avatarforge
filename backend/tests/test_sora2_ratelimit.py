"""Sora 2 client honors 429 rate limits with Retry-After before succeeding."""

import httpx
import pytest

from backend.config import get_settings
from backend.services.scene.sora2_client import Sora2SceneClient


def _client(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "azure_openai_endpoint", "https://r.openai.azure.com", raising=False)
    monkeypatch.setattr(s, "azure_openai_api_key", "k", raising=False)
    return Sora2SceneClient(s)


def test_retry_after_prefers_header():
    resp = httpx.Response(429, headers={"retry-after": "5"})
    assert Sora2SceneClient._retry_after_seconds(resp, 1) == 5.0


def test_retry_after_backoff_without_header():
    resp = httpx.Response(429)
    assert Sora2SceneClient._retry_after_seconds(resp, 3) == 8.0  # 2**3, capped at 90


def test_retry_after_capped():
    resp = httpx.Response(429, headers={"retry-after": "9999"})
    assert Sora2SceneClient._retry_after_seconds(resp, 1) == 90.0


@pytest.mark.asyncio
async def test_create_retries_after_429_then_succeeds(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr("asyncio.sleep", lambda *_a, **_k: _noop())
    state = {"posts": 0}

    def handler(request):
        url = str(request.url)
        if request.method == "POST":
            state["posts"] += 1
            if state["posts"] == 1:
                return httpx.Response(429, headers={"retry-after": "0"}, json={})
            return httpx.Response(200, json={"id": "vid_rl"})
        if "/content" in url:
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
    out = await c.generate("a forest", seconds=4)
    assert out == b"MP4" and state["posts"] == 2  # one 429, then success


async def _noop():
    return None
