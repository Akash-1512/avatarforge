"""Style engine: realistic pass-through, stylized via fal FLUX-LoRA (mocked)."""

import httpx
import pytest

from backend.config import get_settings
from backend.services.style.service import (
    STYLE_REGISTRY,
    SUPPORTED_STYLES,
    StyleEngineError,
    StyleService,
)


def _svc(monkeypatch, key="k"):
    s = get_settings()
    monkeypatch.setattr(s, "fal_api_key", key, raising=False)
    return StyleService(s)


@pytest.mark.asyncio
async def test_realistic_is_passthrough(monkeypatch):
    svc = _svc(monkeypatch)
    assert await svc.restyle(b"ORIGINAL", "realistic") == b"ORIGINAL"


@pytest.mark.asyncio
async def test_unknown_style_rejected(monkeypatch):
    svc = _svc(monkeypatch)
    with pytest.raises(StyleEngineError) as ei:
        await svc.restyle(b"x", "hologram")
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_not_configured(monkeypatch):
    svc = _svc(monkeypatch, key="")
    with pytest.raises(StyleEngineError) as ei:
        await svc.restyle(b"x", "anime")
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_anime_restyle_direct_result(monkeypatch):
    svc = _svc(monkeypatch)

    def handler(request):
        url = str(request.url)
        if "image-to-image" in url:  # submit returns result directly
            return httpx.Response(200, json={"images": [{"url": "https://f/out.jpg"}]})
        if url == "https://f/out.jpg":
            return httpx.Response(200, content=b"STYLED")
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
    out = await svc.restyle(b"PERSON", "anime")
    assert out == b"STYLED"


def test_registry_strengths_sane():
    assert "realistic" in SUPPORTED_STYLES
    for name, spec in STYLE_REGISTRY.items():
        assert 0.0 < spec.strength < 1.0, name
