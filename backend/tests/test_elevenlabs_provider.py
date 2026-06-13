"""ElevenLabs TTS provider: availability gate + synthesis (mocked)."""

import httpx
import pytest

from backend.config import get_settings
from backend.services.tts.base import TTSProviderError
from backend.services.tts.providers import ElevenLabsProvider


def test_unavailable_without_key(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "elevenlabs_api_key", "", raising=False)
    assert ElevenLabsProvider(s).available is False


def test_available_with_key(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "elevenlabs_api_key", "key", raising=False)
    assert ElevenLabsProvider(s).available is True


@pytest.mark.asyncio
async def test_synthesize_returns_audio(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "elevenlabs_api_key", "key", raising=False)
    prov = ElevenLabsProvider(s)

    def handler(request):
        assert "text-to-speech" in str(request.url)
        return httpx.Response(200, content=b"AUDIO")

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: orig(
            *a, transport=transport, **{x: y for x, y in k.items() if x != "transport"}
        ),
    )
    res = await prov.synthesize("hello there", voice_preset="voice123")
    assert res.audio_bytes == b"AUDIO" and res.characters == len("hello there")


@pytest.mark.asyncio
async def test_synthesize_error_normalized(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "elevenlabs_api_key", "key", raising=False)
    prov = ElevenLabsProvider(s)

    def handler(request):
        return httpx.Response(429, text="rate limited")

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: orig(
            *a, transport=transport, **{x: y for x, y in k.items() if x != "transport"}
        ),
    )
    with pytest.raises(TTSProviderError):
        await prov.synthesize("x", voice_preset="v")
