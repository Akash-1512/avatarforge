"""Planner-agent eval: deterministic metrics + offline gate behaviour."""

import pytest

from backend.evals import planner_metrics as pm
from backend.evals import planner_runner as pr
from backend.models.schemas import VideoPlan


def _plan(tone="professional", duration=60, language="en"):
    return VideoPlan(topic="test topic", tone=tone, duration_seconds=duration, language=language)


def test_in_spec_perfect_for_valid_plan():
    assert pm.in_spec_score(_plan()) == 1.0


def test_duration_in_range():
    assert pm.duration_in_range_score(_plan(duration=30), 15, 60) == 1.0
    assert pm.duration_in_range_score(_plan(duration=200), 15, 60) == 0.0


def test_tone_match_specific_and_wildcard():
    assert pm.tone_match_score(_plan(tone="casual"), "casual") == 1.0
    assert pm.tone_match_score(_plan(tone="formal"), "casual") == 0.0
    # wildcard: any allowed tone passes when no specific tone expected
    assert pm.tone_match_score(_plan(tone="enthusiastic"), None) == 1.0


def test_compute_all_keys():
    s = pm.compute_all(_plan(), 15, 300, None)
    assert set(s) == {"plan_in_spec", "plan_duration_in_range", "plan_tone_match"}


class _FakePlanner:
    """Returns in-spec plans — exercises aggregation/gate without an LLM."""

    def __init__(self, tone="professional", duration=45):
        self._tone, self._duration = tone, duration

    async def plan(self, brief: str) -> VideoPlan:
        return _plan(tone=self._tone, duration=self._duration)


@pytest.mark.asyncio
async def test_run_case_scores_a_plan():
    case = {
        "case_id": "c1",
        "brief": "b",
        "expect_tone": "professional",
        "expect_duration_range": (15, 60),
    }
    r = await pr.run_case(_FakePlanner(), case)
    assert r["scores"]["plan_in_spec"] == 1.0
    assert r["error"] is None


@pytest.mark.asyncio
async def test_run_case_records_crash_as_failure():
    class Boom:
        async def plan(self, brief):
            raise ValueError("kaboom")

    case = {"case_id": "c2", "brief": "b", "expect_tone": None, "expect_duration_range": (15, 300)}
    r = await pr.run_case(Boom(), case)
    assert r["scores"]["plan_in_spec"] == 0.0
    assert "kaboom" in r["error"]


def test_aggregate_and_gate():
    results = [
        {
            "case_id": "a",
            "scores": {"plan_in_spec": 1.0, "plan_duration_in_range": 1.0, "plan_tone_match": 1.0},
            "error": None,
        },
        {
            "case_id": "b",
            "scores": {"plan_in_spec": 1.0, "plan_duration_in_range": 0.0, "plan_tone_match": 1.0},
            "error": None,
        },
    ]
    agg = pr.aggregate(results)
    assert agg["plan_in_spec"] == 1.0
    assert agg["plan_duration_in_range"] == 0.5
    # in_spec perfect passes; duration 0.5 < 0.85 threshold -> a failure is reported
    failures = pr.check_thresholds(agg)
    assert any("plan_duration_in_range" in f for f in failures)
    assert not any("plan_in_spec" in f for f in failures)
