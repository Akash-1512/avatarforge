"""TTSService fallback orchestration — fake providers, real ffmpeg + storage."""

import subprocess

import pytest

from backend.models.schemas import TTSRequest
from backend.services.storage.local import LocalStorageBackend
from backend.services.tts.base import (
    AllTTSProvidersFailedError,
    BaseTTSProvider,
    SynthesisResult,
    TTSProviderError,
)
from backend.services.tts.service import TTSService


def _tone_wav() -> bytes:
    return subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-f",
            "wav",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout


class FakeTTS(BaseTTSProvider):
    def __init__(self, name, *, fail=False, configured=True):
        self.name = name
        self._fail = fail
        self._configured = configured
        self.calls = 0

    @property
    def available(self):
        return self._configured

    async def synthesize(self, text, voice_preset, speaking_rate=1.0, language="en"):
        self.calls += 1
        if self._fail:
            raise TTSProviderError(self.name, RuntimeError("simulated outage"))
        return SynthesisResult(audio_bytes=_tone_wav(), model="fake-voice", characters=len(text))


REQ = TTSRequest(text="Hello, this is a test of the speech system.")


@pytest.fixture
def storage(tmp_path):
    return LocalStorageBackend(str(tmp_path))


@pytest.mark.asyncio
async def test_primary_used_when_healthy(storage):
    azure = FakeTTS("azure_speech")
    openai = FakeTTS("openai_tts")
    svc = TTSService([azure, openai], storage)
    resp = await svc.synthesize(REQ)
    assert resp.provider_used == "azure_speech"
    assert openai.calls == 0
    assert resp.audio_duration_sec > 0.5
    assert storage.resolve_path(resp.file_id) is not None


@pytest.mark.asyncio
async def test_fallback_on_primary_failure(storage):
    svc = TTSService([FakeTTS("azure_speech", fail=True), FakeTTS("openai_tts")], storage)
    resp = await svc.synthesize(REQ)
    assert resp.provider_used == "openai_tts"
    assert resp.estimated_cost_usd > 0  # openai path is paid


@pytest.mark.asyncio
async def test_azure_cost_is_zero(storage):
    svc = TTSService([FakeTTS("azure_speech")], storage)
    resp = await svc.synthesize(REQ)
    assert resp.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_all_failed_raises(storage):
    svc = TTSService(
        [FakeTTS("azure_speech", fail=True), FakeTTS("openai_tts", fail=True)], storage
    )
    with pytest.raises(AllTTSProvidersFailedError):
        await svc.synthesize(REQ)


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold(storage):
    azure = FakeTTS("azure_speech", fail=True)
    svc = TTSService(
        [azure, FakeTTS("openai_tts")], storage, failure_threshold=2, recovery_timeout_sec=300
    )
    await svc.synthesize(REQ)
    await svc.synthesize(REQ)
    assert azure.calls == 2
    await svc.synthesize(REQ)  # circuit open — azure skipped
    assert azure.calls == 2


@pytest.mark.asyncio
async def test_cloned_voice_routes_only_to_chatterbox(storage):
    """voice='cloned' is served exclusively by the chatterbox provider."""
    azure = FakeTTS("azure_speech")
    clone = FakeTTS("chatterbox_fal")
    svc = TTSService([azure, clone], storage)
    await svc.synthesize(TTSRequest(text="speak in my cloned voice", voice="cloned"))
    assert clone.calls == 1 and azure.calls == 0


@pytest.mark.asyncio
async def test_standard_voice_never_routes_to_chatterbox(storage):
    """A normal preset never touches the paid clone provider."""
    azure = FakeTTS("azure_speech")
    clone = FakeTTS("chatterbox_fal")
    svc = TTSService([azure, clone], storage)
    await svc.synthesize(TTSRequest(text="standard voice please", voice="professional_female"))
    assert azure.calls == 1 and clone.calls == 0
