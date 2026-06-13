"""Operational metrics endpoint — provider health, fallback rate, spend."""

from fastapi import APIRouter

from backend.services.metrics.summary import compute_summary

router = APIRouter()


@router.get("/metrics/summary")
async def metrics_summary() -> dict:
    """Aggregates from the audit tables: success rates, latencies, costs, jobs."""
    return await compute_summary()


@router.get("/metrics/eval")
async def metrics_eval() -> dict:
    """Latest script-generation eval run: per-metric scores vs regression
    thresholds, judge score, and the pass/fail gate. Populated by `make eval`;
    returns {available: false} until the harness has been run."""
    import json

    from backend.config import get_settings

    path = get_settings().eval_report_path
    try:
        with open(path) as fh:
            report = json.load(fh)
        report["available"] = True
        return report
    except (OSError, ValueError):
        return {"available": False, "hint": "run `make eval` to populate"}
