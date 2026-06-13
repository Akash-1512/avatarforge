"""Prompt-to-video planner — LLM proposes, schema disposes."""

import json

import pytest

from backend.models.schemas import VideoPlan
from backend.services.planner.service import PlannerService


class FakeLLM:
    """Returns a scripted sequence of raw JSON strings from complete_json_raw."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    async def complete_json_raw(self, system_prompt, user_prompt):
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


GOOD = json.dumps(
    {
        "topic": "Compound interest, explained for teenagers",
        "tone": "enthusiastic",
        "duration_seconds": 30,
        "language": "en",
        "voice": "casual_female",
        "engine": "sadtalker",
        "rationale": "Upbeat tone and casual voice suit a teen audience.",
    }
)


@pytest.mark.asyncio
async def test_valid_plan_parsed_first_try():
    svc = PlannerService(FakeLLM(GOOD))
    plan = await svc.plan("explain compound interest to teenagers, upbeat, 30s")
    assert isinstance(plan, VideoPlan)
    assert plan.tone == "enthusiastic"
    assert plan.duration_seconds == 30
    assert plan.voice == "casual_female"


@pytest.mark.asyncio
async def test_strips_markdown_fences():
    fenced = f"```json\n{GOOD}\n```"
    plan = await PlannerService(FakeLLM(fenced)).plan("anything reasonable here")
    assert plan.topic.startswith("Compound interest")


@pytest.mark.asyncio
async def test_hallucinated_value_triggers_retry_then_succeeds():
    bad = json.dumps({**json.loads(GOOD), "voice": "dramatic_baritone"})  # not a valid enum
    llm = FakeLLM(bad, GOOD)
    plan = await PlannerService(llm).plan("brief that triggers a bad first plan")
    assert llm.calls == 2  # retried
    assert plan.voice == "casual_female"


@pytest.mark.asyncio
async def test_out_of_range_duration_rejected_then_retry():
    bad = json.dumps({**json.loads(GOOD), "duration_seconds": 9999})
    llm = FakeLLM(bad, GOOD)
    plan = await PlannerService(llm).plan("brief here")
    assert llm.calls == 2
    assert 15 <= plan.duration_seconds <= 300


@pytest.mark.asyncio
async def test_falls_back_to_defaults_when_both_attempts_invalid():
    llm = FakeLLM("not json at all", "{still: broken")
    plan = await PlannerService(llm).plan("rescue me with a sane default")
    assert llm.calls == 2
    assert isinstance(plan, VideoPlan)
    assert plan.tone == "professional"  # safe default
    assert "rescue me" in plan.topic  # seeded from brief


@pytest.mark.asyncio
async def test_garbage_then_garbage_never_raises():
    plan = await PlannerService(FakeLLM("", "")).plan("a perfectly fine brief")
    assert isinstance(plan, VideoPlan)
