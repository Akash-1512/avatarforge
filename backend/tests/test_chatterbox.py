"""Chatterbox voice-clone provider — mocked fal queue flow + routing rules."""

import httpx
import pytest

from backend.config import Settings
from backend.services.tts.chatterbox import ChatterboxProvider


def _settings(**kw):
    base = dict(fal_api_key="k", voice_clone_reference_url="https://ref/voice.wav")
    base.update(kw)
    return Settings(**base)


class _Mock:
    def __init__(self):
        self.status_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "queue.fal.run" in url and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "status_url": "https://queue.fal.run/x/status",
                    "response_url": "https://queue.fal.run/x",
                },
            )
        if url.endswith("/status"):
            self.status_calls += 1
            if self.status_calls >= 2:
                return httpx.Response(200, json={"status": "COMPLETED"})
            return httpx.Response(202, json={"status": "IN_PROGRESS"})
        return httpx.Response(200, json={"audio": {"url": "https://fal.media/clone.wav"}})


@pytest.fixture
def patch_httpx(monkeypatch):
    mock = _Mock()
    transport = httpx.MockTransport(mock.handler)
    real_init = httpx.AsyncClient.__init__

    def patched(self, *a, **kw):
        kw["transport"] = transport
        real_init(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    async def instant(_):
        return None

    monkeypatch.setattr("asyncio.sleep", instant)
    return mock


def test_available_requires_key_and_reference():
    # Explicitly empty the fields — omitting them lets pydantic-settings read
    # real values from the environment (.env), which would make this flaky.
    assert ChatterboxProvider(_settings()).available is True
    assert (
        ChatterboxProvider(Settings(fal_api_key="k", voice_clone_reference_url="")).available
        is False
    )  # no reference
    assert (
        ChatterboxProvider(
            Settings(fal_api_key="", voice_clone_reference_url="https://r/v.wav")
        ).available
        is False
    )  # no key


@pytest.mark.asyncio
async def test_synthesize_polls_and_returns_audio(patch_httpx):
    out = await ChatterboxProvider(_settings()).synthesize("hello in my voice", "cloned")
    assert isinstance(out.audio_bytes, bytes)
    assert out.model == "chatterbox-hd"
    assert patch_httpx.status_calls >= 2  # polled through 202 then 200