"""Optional DeepEval integration — wraps our metrics as DeepEval custom metrics.

DeepEval pulls a heavy dependency tree, so it lives in requirements-eval.txt
rather than the runtime image. Install and run separately when wanted:

    pip install -r requirements-eval.txt
    python -m backend.evals.deepeval_suite --limit 3
"""

import argparse
import asyncio
import sys

try:
    from deepeval.metrics import BaseMetric
    from deepeval.test_case import LLMTestCase

    DEEPEVAL_AVAILABLE = True
except ImportError:  # pragma: no cover — optional dependency
    DEEPEVAL_AVAILABLE = False
    BaseMetric = object  # type: ignore[assignment,misc]

from backend.evals import metrics as m
from backend.evals.dataset import DATASET
from backend.models.schemas import ScriptPayload, ScriptRequest


class SpeakabilityMetric(BaseMetric):
    """DeepEval custom metric backed by our deterministic speakability check."""

    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold
        self.score = 0.0
        self.success = False

    def measure(self, test_case) -> float:
        payload = ScriptPayload.model_validate_json(test_case.actual_output)
        self.score = m.speakability_score(payload)
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):  # noqa: D105
        return "Speakability"


async def run(limit: int) -> int:
    if not DEEPEVAL_AVAILABLE:
        print("deepeval not installed. Run: pip install -r requirements-eval.txt")
        return 2
    from backend.services.llm.service import get_llm_service

    llm = get_llm_service()
    metric = SpeakabilityMetric()
    failures = 0
    for case in DATASET[:limit]:
        resp = await llm.generate_script(
            ScriptRequest(
                topic=case["topic"],
                tone=case["tone"],
                duration_seconds=case["duration_seconds"],
            )
        )
        payload = ScriptPayload(
            title=resp.title,
            segments=resp.segments,
            total_duration_sec=resp.total_duration_sec,
        )
        tc = LLMTestCase(input=case["topic"], actual_output=payload.model_dump_json())
        score = metric.measure(tc)
        status = "PASS" if metric.is_successful() else "FAIL"
        print(f"[{case['case_id']}] speakability={score:.2f} {status}")
        failures += 0 if metric.is_successful() else 1
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.limit)))
