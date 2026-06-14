"""Voiceover: dialogue -> audio bytes via the provider chain, resilient."""

import pytest

from backend.services.voice.service import VoiceoverService


class _Prov:
    def __init__(self, name, available, audio=b"AUD", fail=False):
        self.name = name
        self.available = available
        self._audio = audio
        self._fail = fail

    async def synthesize(self, text, voice_preset=None, language="en"):
        if self._fail:
            raise RuntimeError("boom")
        from backend.services.tts.base import SynthesisResult

        return SynthesisResult(audio_bytes=self._audio, model="m", characters=len(text))


@pytest.mark.asyncio
async def test_returns_none_for_empty_text():
    assert await VoiceoverService(providers=[_Prov("a", True)]).speak("") is None


@pytest.mark.asyncio
async def test_uses_first_available_provider():
    svc = VoiceoverService(providers=[_Prov("azure", False), _Prov("eleven", True, b"VOICE")])
    assert await svc.speak("hello") == b"VOICE"  # skipped unavailable azure


@pytest.mark.asyncio
async def test_falls_through_failing_provider():
    svc = VoiceoverService(providers=[_Prov("a", True, fail=True), _Prov("b", True, b"OK")])
    assert await svc.speak("hi") == b"OK"


@pytest.mark.asyncio
async def test_none_when_all_unavailable():
    assert await VoiceoverService(providers=[_Prov("a", False)]).speak("hi") is None


@pytest.mark.asyncio
async def test_describes_voice_resolved_before_synthesis(monkeypatch):
    """A plain-language voice is resolved to a concrete voice before TTS."""
    captured = {}

    class _Prov:
        name = "azure"
        available = True

        async def synthesize(self, text, voice_preset=None, language="en"):
            from backend.services.tts.base import SynthesisResult

            captured["preset"] = voice_preset
            return SynthesisResult(audio_bytes=b"AUD", model="m", characters=len(text))

    import backend.services.voice.resolver as resolver_mod

    class _Resolver:
        async def resolve(self, desc, language="en"):
            return "en-US-ResolvedNeural"

    monkeypatch.setattr(resolver_mod, "get_voice_resolver", lambda: _Resolver())
    out = await VoiceoverService(providers=[_Prov()]).speak("hello", voice="a warm baritone")
    assert out == b"AUD"
    assert captured["preset"] == "en-US-ResolvedNeural"  # described -> resolved


@pytest.mark.asyncio
async def test_explicit_voice_id_skips_resolution():
    """An explicit voice id is passed straight through, no resolver call."""
    captured = {}

    class _Prov:
        name = "azure"
        available = True

        async def synthesize(self, text, voice_preset=None, language="en"):
            from backend.services.tts.base import SynthesisResult

            captured["preset"] = voice_preset
            return SynthesisResult(audio_bytes=b"AUD", model="m", characters=len(text))

    out = await VoiceoverService(providers=[_Prov()]).speak("hi", voice="en-US-JennyNeural")
    assert out == b"AUD" and captured["preset"] == "en-US-JennyNeural"
