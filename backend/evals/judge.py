"""LLM-as-Judge for script quality — the G-Eval pattern.

A separate judging prompt scores dimensions deterministic metrics can't
measure: hook strength, flow, tone match, spoken naturalness. The judge
reuses LLMService (same fallback/circuit-breaker/audit machinery), reads
a strict rubric, and must answer in JSON with a brief justification per
dimension — chain-of-thought-then-score, which measurably improves
judge reliability.
"""

import json
from typing import Dict

from pydantic import BaseModel, Field

from backend.models.schemas import ScriptPayload

JUDGE_SYSTEM_PROMPT = """You are a strict evaluator of short video narration scripts. \
You score scripts on a 1-5 scale per dimension using the rubric. Be harsh: 5 means \
genuinely excellent, 3 means acceptable, 1 means unusable. Respond ONLY with JSON, \
no markdown, matching exactly:
{"hook": {"reason": str, "score": int}, "flow": {"reason": str, "score": int},
 "tone_match": {"reason": str, "score": int}, "spoken_naturalness": {"reason": str, "score": int}}

Rubric:
- hook: Does the first segment grab attention in the first sentence? (5: impossible to \
stop listening; 1: generic throat-clearing like 'In this video we will...')
- flow: Do segments connect logically with smooth transitions? (5: seamless narrative; \
1: disconnected bullet points read aloud)
- tone_match: Does the language match the requested tone? (5: perfectly calibrated; \
1: wrong register entirely)
- spoken_naturalness: Does it sound like a human talking, not an essay? Contractions, \
direct address, short sentences. (5: completely natural speech; 1: written prose)"""


class DimensionScore(BaseModel):
    reason: str
    score: int = Field(ge=1, le=5)


class JudgeVerdict(BaseModel):
    hook: DimensionScore
    flow: DimensionScore
    tone_match: DimensionScore
    spoken_naturalness: DimensionScore

    def scores(self) -> Dict[str, float]:
        return {
            "judge_hook": float(self.hook.score),
            "judge_flow": float(self.flow.score),
            "judge_tone_match": float(self.tone_match.score),
            "judge_spoken_naturalness": float(self.spoken_naturalness.score),
            "judge_overall": round(
                (
                    self.hook.score
                    + self.flow.score
                    + self.tone_match.score
                    + self.spoken_naturalness.score
                )
                / 4,
                2,
            ),
        }


def build_judge_prompt(payload: ScriptPayload, tone: str, topic: str) -> str:
    segments = "\n".join(f"[{s.index}] {s.text}" for s in payload.segments)
    return (
        f"Requested topic: {topic}\nRequested tone: {tone}\n\n"
        f"Script title: {payload.title}\nSegments:\n{segments}\n\n"
        "Score this script per the rubric. JSON only."
    )


async def judge_script(llm_service, payload: ScriptPayload, tone: str, topic: str) -> JudgeVerdict:
    """Run the judge through the first healthy provider of LLMService."""
    user_prompt = build_judge_prompt(payload, tone, topic)
    raw = await llm_service.complete_json_raw(JUDGE_SYSTEM_PROMPT, user_prompt)
    return JudgeVerdict.model_validate(json.loads(raw))
