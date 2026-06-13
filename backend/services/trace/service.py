"""Per-job trace — reconstruct one job as an end-to-end pipeline trace.

Joins the three audit tables on the job_id correlation column written during
the run, and presents them as ordered pipeline stages. Each stage carries the
provider that served it, the cost and latency, and — for the LLM stage — token
counts and whether a fallback fired (more than one provider row, or a
non-primary provider succeeding). This is what makes a single request legible:
which model answered, what it cost, how long it took, and where it failed over.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.models.avatar_usage import AvatarUsage
from backend.models.tts_usage import TTSUsage
from backend.models.usage import TokenUsage

_PRIMARY_LLM = "azure_openai"
_PRIMARY_TTS = "azure_speech"


async def build_trace(job_id: str, session_factory: Optional[async_sessionmaker] = None) -> dict:
    if session_factory is None:
        from backend.models.db import get_session_factory

        session_factory = get_session_factory()

    async with session_factory() as s:
        from backend.models.job import VideoJob

        job = await s.get(VideoJob, job_id)
        if job is None:
            return {"found": False}

        llm_rows = (
            (
                await s.execute(
                    select(TokenUsage).where(TokenUsage.job_id == job_id).order_by(TokenUsage.id)
                )
            )
            .scalars()
            .all()
        )
        tts_rows = (
            (
                await s.execute(
                    select(TTSUsage).where(TTSUsage.job_id == job_id).order_by(TTSUsage.id)
                )
            )
            .scalars()
            .all()
        )
        av_rows = (
            (
                await s.execute(
                    select(AvatarUsage).where(AvatarUsage.job_id == job_id).order_by(AvatarUsage.id)
                )
            )
            .scalars()
            .all()
        )

        timings = job.stage_timings or {}

        def llm_stage():
            if not llm_rows:
                return None
            winner = next((r for r in llm_rows if r.success), llm_rows[-1])
            providers = [r.provider for r in llm_rows]
            fell_back = winner.provider != _PRIMARY_LLM or any(not r.success for r in llm_rows)
            return {
                "stage": "script",
                "label": "Script generation",
                "provider": winner.provider,
                "providers_tried": providers,
                "fell_back": fell_back,
                "prompt_tokens": winner.prompt_tokens,
                "completion_tokens": winner.completion_tokens,
                "total_tokens": winner.total_tokens,
                "cost_usd": round(sum(r.estimated_cost_usd for r in llm_rows), 6),
                "latency_ms": winner.latency_ms,
                "success": winner.success,
                "attempts": len(llm_rows),
            }

        def tts_stage():
            if not tts_rows:
                return None
            winner = next((r for r in tts_rows if r.success), tts_rows[-1])
            fell_back = winner.provider != _PRIMARY_TTS or any(not r.success for r in tts_rows)
            return {
                "stage": "tts",
                "label": "Voice synthesis",
                "provider": winner.provider,
                "providers_tried": [r.provider for r in tts_rows],
                "fell_back": fell_back,
                "characters": winner.characters,
                "audio_duration_sec": winner.audio_duration_sec,
                "cost_usd": round(sum(r.estimated_cost_usd for r in tts_rows), 6),
                "latency_ms": winner.latency_ms,
                "success": winner.success,
                "attempts": len(tts_rows),
            }

        def avatar_stage():
            if not av_rows:
                return None
            winner = next((r for r in av_rows if r.success), av_rows[-1])
            return {
                "stage": "avatar",
                "label": "Avatar render",
                "provider": winner.engine,
                "providers_tried": [r.engine for r in av_rows],
                "fell_back": False,
                "video_duration_sec": winner.video_duration_sec,
                "cost_usd": 0.0,
                "latency_ms": winner.latency_ms,
                "success": winner.success,
                "attempts": len(av_rows),
            }

        stages = [s for s in (llm_stage(), tts_stage(), avatar_stage()) if s]
        total_latency = sum(s["latency_ms"] for s in stages) or 1
        for st in stages:
            st["latency_pct"] = round(st["latency_ms"] / total_latency * 100, 1)

        return {
            "found": True,
            "job_id": job_id,
            "status": job.status,
            "current_stage": job.current_stage,
            "engine": job.engine,
            "language": job.language,
            "script_title": job.script_title,
            "error_type": job.error_type,
            "error_message": job.error_message,
            "stage_timings_ms": timings,
            "stages": stages,
            "total_cost_usd": round(sum(s["cost_usd"] for s in stages), 6),
            "total_latency_ms": sum(s["latency_ms"] for s in stages),
        }
