"""Operational metrics endpoint — provider health, fallback rate, spend."""

from fastapi import APIRouter

from backend.services.metrics.summary import compute_summary

router = APIRouter()


@router.get("/metrics/summary")
async def metrics_summary() -> dict:
    """Aggregates from the audit tables: success rates, latencies, costs, jobs."""
    return await compute_summary()
