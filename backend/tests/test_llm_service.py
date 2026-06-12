"""LLMService fallback orchestration — fake providers, no network."""

import json

import pytest

from backend.models.schemas import ScriptRequest
from backend.services.llm.base import (
    AllProvidersFailedError,
    BaseLLMProvider,
    CompletionResult,
    LLMProviderError,
)
from backend.services.llm.service import LLMService, estimate_cost_usd

VALID_SCRIPT = json.dumps(
    {
        "title": "Test video",
        "segments": [
            {"index": 0, "text": "Hello and welcome.", "est_duration_sec": 5.0},
            {"index": 1, "text": "This is a test script.", "est_duration_sec": 5.0},
        ],
        "total_duration_sec": 10.0,
    }
)


class FakeProvider(BaseLLMProvider):
    def __init__(
        self, name: str, *, fail: bool = False, content: str = VALID_SCRIPT, configured: bool = True
    ):
        self.name = name
        self._fail = fail
        self._content = content
        self._configured = configured
        self.calls = 0

    @property
    def available(self) -> bool:
        return self._configured

    async def complete_json(self, system, user, max_tokens=1500) -> CompletionResult:
        self.calls += 1
        if self._fail:
            raise LLMProviderError(self.name, RuntimeError("simulated outage"))
        return CompletionResult(
            content=self._content,
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=200,
        )


REQ = ScriptRequest(topic="The benefits of morning exercise", duration_seconds=30)


@pytest.mark.asyncio
async def test_primary_provider_used_when_healthy():
    azure = FakeProvider("azure_openai")
    openai = FakeProvider("openai")
    svc = LLMService([azure, openai])
    resp = await svc.generate_script(REQ)
    assert resp.provider_used == "azure_openai"
    assert azure.calls == 1 and openai.calls == 0
    assert len(resp.segments) == 2
    assert resp.usage.total_tokens == 300


@pytest.mark.asyncio
async def test_fallback_fires_when_primary_fails():
    azure = FakeProvider("azure_openai", fail=True)
    openai = FakeProvider("openai")
    svc = LLMService([azure, openai])
    resp = await svc.generate_script(REQ)
    assert resp.provider_used == "openai"
    assert azure.calls == 1 and openai.calls == 1


@pytest.mark.asyncio
async def test_unconfigured_provider_skipped_without_calling():
    azure = FakeProvider("azure_openai", configured=False)
    openai = FakeProvider("openai")
    svc = LLMService([azure, openai])
    resp = await svc.generate_script(REQ)
    assert resp.provider_used == "openai"
    assert azure.calls == 0


@pytest.mark.asyncio
async def test_invalid_json_triggers_fallback():
    azure = FakeProvider("azure_openai", content="this is not json at all")
    openai = FakeProvider("openai")
    svc = LLMService([azure, openai])
    resp = await svc.generate_script(REQ)
    assert resp.provider_used == "openai"


@pytest.mark.asyncio
async def test_schema_violation_triggers_fallback():
    bad = json.dumps({"title": "x", "segments": [], "total_duration_sec": 10})
    azure = FakeProvider("azure_openai", content=bad)
    openai = FakeProvider("openai")
    svc = LLMService([azure, openai])
    resp = await svc.generate_script(REQ)
    assert resp.provider_used == "openai"


@pytest.mark.asyncio
async def test_all_failed_raises():
    svc = LLMService(
        [
            FakeProvider("azure_openai", fail=True),
            FakeProvider("openai", fail=True),
        ]
    )
    with pytest.raises(AllProvidersFailedError):
        await svc.generate_script(REQ)


@pytest.mark.asyncio
async def test_circuit_opens_and_skips_provider():
    azure = FakeProvider("azure_openai", fail=True)
    openai = FakeProvider("openai")
    svc = LLMService([azure, openai], failure_threshold=2, recovery_timeout_sec=300)

    await svc.generate_script(REQ)  # azure fail 1 -> openai
    await svc.generate_script(REQ)  # azure fail 2 -> circuit opens -> openai
    assert azure.calls == 2

    await svc.generate_script(REQ)  # azure skipped entirely
    assert azure.calls == 2
    assert not svc.breakers["azure_openai"].allow_request()


@pytest.mark.asyncio
async def test_usage_recorder_called_on_success_and_failure():
    recorded = []

    async def recorder(payload):
        recorded.append(payload)

    svc = LLMService(
        [FakeProvider("azure_openai", fail=True), FakeProvider("openai")],
        usage_recorder=recorder,
    )
    await svc.generate_script(REQ)
    assert len(recorded) == 2
    assert recorded[0]["success"] is False and recorded[0]["provider"] == "azure_openai"
    assert recorded[1]["success"] is True and recorded[1]["provider"] == "openai"


@pytest.mark.asyncio
async def test_db_recorder_failure_does_not_break_request():
    async def broken_recorder(payload):
        raise RuntimeError("db is down")

    svc = LLMService([FakeProvider("openai")], usage_recorder=broken_recorder)
    resp = await svc.generate_script(REQ)
    assert resp.provider_used == "openai"


def test_cost_estimation():
    assert estimate_cost_usd("gpt-4o-mini-2024", 1_000_000, 0) == 0.15
    assert estimate_cost_usd("gpt-4o-mini", 0, 1_000_000) == 0.60
    assert estimate_cost_usd("unknown-model", 1000, 1000) == 0.0


class FakeJsonProvider:
    """Minimal provider for exercising complete_json_raw on the REAL class."""

    name = "azure_openai"

    def __init__(self, content='{"ok": true}', fail=False):
        self._content = content
        self._fail = fail

    async def complete_json(self, system_prompt, user_prompt):
        if self._fail:
            raise RuntimeError("provider down")
        from types import SimpleNamespace

        return SimpleNamespace(
            content=self._content, model="fake", prompt_tokens=1, completion_tokens=1
        )


@pytest.mark.asyncio
async def test_complete_json_raw_uses_real_internals():
    """Guards against drift between auxiliary paths and real class internals."""
    svc = LLMService([FakeJsonProvider()])
    out = await svc.complete_json_raw("sys", "user")
    assert out == '{"ok": true}'


@pytest.mark.asyncio
async def test_complete_json_raw_raises_when_all_fail():
    svc = LLMService([FakeJsonProvider(fail=True)])
    with pytest.raises(AllProvidersFailedError):
        await svc.complete_json_raw("sys", "user")