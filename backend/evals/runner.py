"""Eval harness runner — the prompt-regression gate.

Runs the dataset through script generation, computes deterministic
metrics, optionally consults the LLM judge, aggregates, logs everything
to MLflow as one experiment run, and exits non-zero when any aggregate
falls below threshold. Run it before merging any prompt or model change:

    python -m backend.evals.runner                 # full run
    python -m backend.evals.runner --limit 3       # quick smoke
    python -m backend.evals.runner --no-judge      # deterministic only
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from typing import Dict, List, Optional

from backend.evals import metrics as m
from backend.evals.dataset import DATASET
from backend.evals.judge import judge_script
from backend.models.schemas import ScriptPayload, ScriptRequest
from backend.observability.logging import get_logger

logger = get_logger(__name__)

# Regression thresholds — aggregates below these fail the run (exit 1).
THRESHOLDS: Dict[str, float] = {
    "duration_accuracy": 0.70,
    "spoken_duration_consistency": 0.55,
    "segment_pacing": 0.80,
    "speakability": 0.95,
    "structure": 0.99,
    "judge_overall": 3.2,  # only enforced when the judge runs
}


async def run_case(llm_service, case, use_judge: bool) -> Dict:
    started = time.monotonic()
    resp = await llm_service.generate_script(
        ScriptRequest(
            topic=case["topic"],
            tone=case["tone"],
            duration_seconds=case["duration_seconds"],
        )
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    payload = ScriptPayload(
        title=resp.title,
        segments=resp.segments,
        total_duration_sec=resp.total_duration_sec,
    )
    scores = m.compute_all(payload, case["duration_seconds"])
    judge_error: Optional[str] = None
    if use_judge:
        try:
            verdict = await judge_script(llm_service, payload, case["tone"], case["topic"])
            scores.update(verdict.scores())
        except Exception as exc:  # noqa: BLE001 — judge failure shouldn't kill the run
            judge_error = f"{type(exc).__name__}: {exc}"
            logger.warning("judge_failed", case_id=case["case_id"], error=judge_error[:200])
    return {
        "case_id": case["case_id"],
        "topic": case["topic"],
        "title": resp.title,
        "provider": resp.provider_used,
        "latency_ms": latency_ms,
        "cost_usd": resp.usage.estimated_cost_usd,
        "scores": scores,
        "judge_error": judge_error,
    }


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


def write_local_report(
    results: List[Dict], aggregates: Dict[str, float], failures: List[str]
) -> None:
    """Persist the latest eval run to a local JSON file the API can serve.

    Decoupled from MLflow on purpose: the operator console reads this file via
    GET /metrics/eval, so eval results are visible even when MLflow isn't wired.
    """
    from backend.config import get_settings

    path = get_settings().eval_report_path
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases": len(results),
        "aggregates": aggregates,
        "thresholds": THRESHOLDS,
        "failures": failures,
        "passed": not failures,
        "total_cost_usd": round(sum(r["cost_usd"] for r in results), 6),
        "results": [
            {k: r[k] for k in ("case_id", "topic", "provider", "latency_ms", "scores")}
            for r in results
        ],
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(report, fh, indent=2)
        logger.info("eval_report_written", path=path)
    except OSError as exc:
        logger.warning("eval_report_write_failed", error=str(exc)[:200])


def log_to_mlflow(results: List[Dict], aggregates: Dict[str, float], failures: List[str]) -> None:
    from backend.config import get_settings
    from backend.observability import tracking

    if not tracking.enabled():
        logger.info("mlflow_disabled_skipping_eval_log")
        return
    try:
        import mlflow

        settings = get_settings()
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(f"{settings.mlflow_experiment}-evals")
        with mlflow.start_run(run_name=f"eval-{time.strftime('%Y%m%d-%H%M%S')}"):
            mlflow.set_tags(
                {
                    "eval_cases": str(len(results)),
                    "regression_gate": "failed" if failures else "passed",
                }
            )
            for k, v in aggregates.items():
                mlflow.log_metric(k, v)
            mlflow.log_metric("total_cost_usd", round(sum(r["cost_usd"] for r in results), 6))
            mlflow.log_dict({"results": results, "failures": failures}, "eval_report.json")
        logger.info("eval_logged_to_mlflow", cases=len(results))
    except Exception as exc:  # noqa: BLE001
        logger.warning("mlflow_eval_logging_failed", error=str(exc)[:200])


async def run(limit: Optional[int], use_judge: bool) -> int:
    from backend.services.llm.service import get_llm_service

    llm_service = get_llm_service()
    cases = DATASET[:limit] if limit else DATASET
    print(f"Running eval: {len(cases)} cases, judge={'on' if use_judge else 'off'}\n")

    results = []
    for case in cases:
        r = await run_case(llm_service, case, use_judge)
        results.append(r)
        flat = "  ".join(f"{k}={v}" for k, v in r["scores"].items())
        print(f"  [{r['case_id']}] {r['provider']} {r['latency_ms']}ms  {flat}")

    aggregates = aggregate(results)
    failures = check_thresholds(aggregates)
    log_to_mlflow(results, aggregates, failures)
    write_local_report(results, aggregates, failures)

    print("\n=== Aggregates ===")
    for k, v in sorted(aggregates.items()):
        marker = ""
        if k in THRESHOLDS:
            marker = "  PASS" if v >= THRESHOLDS[k] else f"  FAIL (min {THRESHOLDS[k]})"
        print(f"  {k:32} {v}{marker}")
    print(f"  total_cost_usd                   {round(sum(r['cost_usd'] for r in results), 6)}")

    if failures:
        print("\nREGRESSION GATE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nRegression gate: PASSED")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="avatarforge script-generation eval harness")
    parser.add_argument("--limit", type=int, default=None, help="run only first N cases")
    parser.add_argument("--no-judge", action="store_true", help="skip LLM-as-Judge scoring")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.limit, use_judge=not args.no_judge)))


if __name__ == "__main__":
    main()
