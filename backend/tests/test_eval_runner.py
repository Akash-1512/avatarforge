"""Runner — aggregation, threshold gate, judge-failure tolerance."""

import pytest

from backend.evals import runner
from backend.evals.dataset import DATASET
from backend.models.schemas import ScriptResponse, ScriptSegment, TokenUsageInfo

GOOD_SEGMENTS = [
    ScriptSegment(
        index=0,
        text="Ever wonder why a short walk clears your head? Here's the thing.",
        est_duration_sec=7,
    ),
    ScriptSegment(
        index=1,
        text="Movement boosts blood flow to your brain, and focus follows fast.",
        est_duration_sec=8,
    ),
]


class FakeLLM:
    async def generate_script(self, req):
        return ScriptResponse(
            title="Why Walks Work",
            segments=GOOD_SEGMENTS,
            total_duration_sec=req.duration_seconds,
            provider_used="azure_openai",
            model="gpt-4.1-mini",
            latency_ms=5,
            usage=TokenUsageInfo(
                prompt_tokens=10, completion_tokens=20, total_tokens=30, estimated_cost_usd=0.0001
            ),
        )

    async def complete_json_raw(self, system_prompt, user_prompt):
        return (
            '{"hook": {"reason": "r", "score": 4}, "flow": {"reason": "r", "score": 4},'
            ' "tone_match": {"reason": "r", "score": 4},'
            ' "spoken_naturalness": {"reason": "r", "score": 4}}'
        )


class JudgeBrokenLLM(FakeLLM):
    async def complete_json_raw(self, system_prompt, user_prompt):
        raise RuntimeError("judge provider down")


@pytest.mark.asyncio
async def test_run_case_with_judge():
    r = await runner.run_case(FakeLLM(), DATASET[2], use_judge=True)
    assert r["scores"]["structure"] == 1.0
    assert r["scores"]["judge_overall"] == 4.0
    assert r["judge_error"] is None


@pytest.mark.asyncio
async def test_judge_failure_does_not_kill_run():
    r = await runner.run_case(JudgeBrokenLLM(), DATASET[2], use_judge=True)
    assert "judge_overall" not in r["scores"]
    assert "judge provider down" in r["judge_error"]
    assert r["scores"]["speakability"] == 1.0  # deterministic metrics still computed


def test_aggregate_and_threshold_gate():
    results = [
        {"scores": {"speakability": 1.0, "structure": 1.0}},
        {"scores": {"speakability": 0.5, "structure": 1.0}},
    ]
    agg = runner.aggregate(results)
    assert agg["speakability"] == 0.75
    failures = runner.check_thresholds(agg)
    assert any("speakability" in f for f in failures)  # 0.75 < 0.95
    assert not any("structure" in f for f in failures)
