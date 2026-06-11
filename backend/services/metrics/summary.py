"""Operational metrics computed from the audit tables.

The audit rows written by every AI call become queryable product metrics:
provider success/fallback rates, latencies, and spend — no extra
infrastructure, just SQL over data we already keep.
"""

from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.models.avatar_usage import AvatarUsage
from backend.models.job import VideoJob
from backend.models.tts_usage import TTSUsage
from backend.models.usage import TokenUsage


async def compute_summary(session_factory: Optional[async_sessionmaker] = None) -> dict:
    if session_factory is None:
        from backend.models.db import get_session_factory

        session_factory = get_session_factory()

    async with session_factory() as s:

        async def provider_stats(model_cls, cost_col):
            rows = await s.execute(
                select(
                    model_cls.provider,
                    func.count().label("calls"),
                    func.sum(case((model_cls.success.is_(True), 1), else_=0)).label("ok"),
                    func.avg(model_cls.latency_ms).label("avg_latency_ms"),
                    func.coalesce(func.sum(cost_col), 0.0).label("cost_usd"),
                ).group_by(model_cls.provider)
            )
            return {
                r.provider: {
                    "calls": r.calls,
                    "success_rate": round((r.ok or 0) / r.calls, 3) if r.calls else 0.0,
                    "avg_latency_ms": int(r.avg_latency_ms or 0),
                    "cost_usd": round(float(r.cost_usd), 6),
                }
                for r in rows
            }

        llm = await provider_stats(TokenUsage, TokenUsage.estimated_cost_usd)
        tts = await provider_stats(TTSUsage, TTSUsage.estimated_cost_usd)

        avatar_rows = await s.execute(
            select(
                func.count().label("calls"),
                func.sum(case((AvatarUsage.success.is_(True), 1), else_=0)).label("ok"),
                func.avg(AvatarUsage.latency_ms).label("avg_latency_ms"),
            )
        )
        a = avatar_rows.one()
        jobs_rows = await s.execute(select(VideoJob.status, func.count()).group_by(VideoJob.status))
        jobs_by_status = {status: count for status, count in jobs_rows}

    # Fallback rate: share of successful LLM calls served by a non-primary provider.
    llm_ok_calls = {p: v["calls"] * v["success_rate"] for p, v in llm.items()}
    total_ok = sum(llm_ok_calls.values())
    fallback_ok = sum(v for p, v in llm_ok_calls.items() if p != "azure_openai")
    return {
        "llm_providers": llm,
        "llm_fallback_rate": round(fallback_ok / total_ok, 3) if total_ok else 0.0,
        "tts_providers": tts,
        "avatar": {
            "calls": a.calls,
            "success_rate": round((a.ok or 0) / a.calls, 3) if a.calls else 0.0,
            "avg_latency_ms": int(a.avg_latency_ms or 0),
        },
        "jobs_by_status": jobs_by_status,
        "total_cost_usd": round(
            sum(v["cost_usd"] for v in llm.values()) + sum(v["cost_usd"] for v in tts.values()), 6
        ),
    }
