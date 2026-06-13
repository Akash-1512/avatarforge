"""Planner-agent eval harness — the agentic regression gate.

Runs the planner over a diverse and adversarial brief dataset, scores each
produced plan with deterministic metrics, aggregates, and exits non-zero if any
aggregate drops below threshold. This complements the script eval (which scores
generation quality) by gating the *agent's* core guarantee: it always emits an
in-spec, intent-faithful VideoPlan, clamping or defaulting rather than crashing.

    python -m backend.evals.planner_runner            # full run
    python -m backend.evals.planner_runner --limit 3  # smoke
"""

import argparse
import asyncio
import statistics
from typing import Dict, List

import structlog

from backend.evals import planner_metrics as pm
from backend.evals.planner_dataset import PLANNER_DATASET

logger = structlog.get_logger(__name__)

# Agent guarantees are strict: in-spec must be perfect; intent faithfulness high.
THRESHOLDS = {
    "plan_in_spec": 1.0,
    "plan_duration_in_range": 0.85,
    "plan_tone_match": 0.75,
}


async def run_case(planner, case) -> Dict:
    lo, hi = case["expect_duration_range"]
    error = None
    try:
        plan = await planner.plan(case["brief"])
        scores = pm.compute_all(plan, lo, hi, case["expect_tone"])
    except Exception as exc:  # noqa: BLE001 — a crash is itself a failure to record
        error = f"{type(exc).__name__}: {exc}"
        logger.warning("planner_case_failed", case_id=case["case_id"], error=error[:200])
        scores = {"plan_in_spec": 0.0, "plan_duration_in_range": 0.0, "plan_tone_match": 0.0}
    return {"case_id": case["case_id"], "scores": scores, "error": error}


def aggregate(results: List[Dict]) -> Dict[str, float]:
    agg: Dict[str, List[float]] = {}
    for r in results:
        for k, v in r["scores"].items():
            agg.setdefault(k, []).append(v)
    return {k: round(statistics.mean(v), 3) for k, v in agg.items()}


def check_thresholds(aggregates: Dict[str, float]) -> List[str]:
    failures = []
    for metric, minimum in THRESHOLDS.items():
        if metric in aggregates and aggregates[metric] < minimum:
            failures.append(f"{metric}: {aggregates[metric]} < {minimum}")
    return failures


async def main(limit: int | None = None) -> int:
    from backend.services.planner.service import get_planner_service

    planner = get_planner_service()
    cases = PLANNER_DATASET[:limit] if limit else PLANNER_DATASET
    results = [await run_case(planner, c) for c in cases]
    aggregates = aggregate(results)
    failures = check_thresholds(aggregates)

    logger.info(
        "planner_eval_complete", cases=len(results), aggregates=aggregates, passed=not failures
    )
    print("\n=== Planner agent eval ===")
    for k, v in aggregates.items():
        bar = "PASS" if k not in THRESHOLDS or v >= THRESHOLDS[k] else "FAIL"
        print(f"  {k:28s} {v:.3f}  [{bar}]")
    if failures:
        print("\nRegression gate FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nRegression gate passed.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.limit)))
