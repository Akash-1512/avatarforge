"""Described-voice resolution: free text -> concrete voice, with fallback."""

import pytest

from backend.services.voice.resolver import VoiceResolver


class _LLM:
    def __init__(self, role="professional_female", fail=False):
        self._role = role
        self._fail = fail

    async def complete_json_raw(self, system, user):
        if self._fail:
            raise RuntimeError("llm down")
        return f'{{"role":"{self._role}","gender":"female","tone":"warm"}}'


@pytest.mark.asyncio
async def test_passthrough_voice_id():
    r = VoiceResolver(llm=_LLM())
    assert await r.resolve("en-US-JennyNeural") == "en-US-JennyNeural"
    assert await r.resolve("nova") == "nova"


@pytest.mark.asyncio
async def test_role_resolves_to_concrete_voice():
    r = VoiceResolver(llm=_LLM())
    out = await r.resolve("narrator")
    assert out and out != "narrator"  # mapped to a concrete azure voice


@pytest.mark.asyncio
async def test_description_uses_llm_role():
    r = VoiceResolver(llm=_LLM(role="casual_male"))
    assert await r.role_for("a chill, friendly guy") == "casual_male"


@pytest.mark.asyncio
async def test_empty_description_defaults_to_narrator():
    r = VoiceResolver(llm=_LLM())
    out = await r.resolve("")
    assert out  # a usable voice, never empty


@pytest.mark.asyncio
async def test_keyword_fallback_when_llm_fails():
    r = VoiceResolver(llm=_LLM(fail=True))
    assert await r.role_for("a deep male baritone") == "professional_male"
    assert await r.role_for("a warm friendly woman") == "casual_female"
    assert await r.role_for("a documentary narrator") == "narrator"
    assert await r.role_for("a soft soprano") == "professional_female"


@pytest.mark.asyncio
async def test_ambiguous_gender_falls_back_to_narrator():
    r = VoiceResolver(llm=_LLM(fail=True))
    assert await r.role_for("a clear, neutral voice") == "narrator"
