"""LLM-as-Judge — prompt building and verdict parsing with a fake LLM."""

import json

import pytest

from backend.evals.judge import JudgeVerdict, build_judge_prompt, judge_script
from backend.models.schemas import ScriptPayload, ScriptSegment

PAYLOAD = ScriptPayload(
    title="Walks",
    total_duration_sec=15,
    segments=[ScriptSegment(index=0, text="Ever wonder why walks help?", est_duration_sec=15)],
)

VERDICT_JSON = json.dumps(
    {
        "hook": {"reason": "strong question opener", "score": 4},
        "flow": {"reason": "single segment", "score": 3},
        "tone_match": {"reason": "casual as requested", "score": 5},
        "spoken_naturalness": {"reason": "conversational", "score": 4},
    }
)


class FakeLLM:
    async def complete_json_raw(self, system_prompt, user_prompt):
        assert "rubric" in system_prompt.lower()
        return VERDICT_JSON


@pytest.mark.asyncio
async def test_judge_returns_validated_verdict():
    verdict = await judge_script(FakeLLM(), PAYLOAD, "casual", "walks")
    scores = verdict.scores()
    assert scores["judge_hook"] == 4.0
    assert scores["judge_overall"] == 4.0


def test_verdict_rejects_out_of_range():
    bad = json.loads(VERDICT_JSON)
    bad["hook"]["score"] = 9
    with pytest.raises(Exception):
        JudgeVerdict.model_validate(bad)


def test_prompt_contains_script_and_tone():
    prompt = build_judge_prompt(PAYLOAD, "casual", "walks")
    assert "Ever wonder why walks help?" in prompt
    assert "casual" in prompt
