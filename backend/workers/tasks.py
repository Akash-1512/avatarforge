"""Celery tasks.

avatarforge.generate_video wraps the full LangGraph pipeline. Limits are
sized for CPU inference (~50 min worst case). A last-resort handler marks
the job failed even when the exception bypasses the pipeline's own error
handling (e.g. SoftTimeLimitExceeded raised inside the event loop), so no
job is ever orphaned in 'running'.
"""

import asyncio
import time

from backend.workers.celery_app import celery_app


@celery_app.task(name="avatarforge.ping")
def ping(payload: str = "pong") -> dict:
    """Smoke test — verifies broker round-trip and result backend."""
    time.sleep(1)
    return {"echo": payload, "worker": "alive"}


@celery_app.task(
    name="avatarforge.generate_video",
    bind=True,
    soft_time_limit=3300,  # 55 min — CPU inference budget
    time_limit=3600,       # hard kill at 60 min
)
def generate_video_task(self, job_id: str) -> dict:
    """Execute the full video pipeline for a queued job."""
    from backend.agents.pipeline import get_default_nodes, push_dead_letter, run_pipeline
    from backend.services.jobs.repository import get_job_repository

    repo = get_job_repository()

    async def _run() -> dict:
        await repo.mark_running(job_id, celery_task_id=self.request.id)
        return await run_pipeline(job_id, get_default_nodes(), repo)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        # Last resort: if the pipeline's own handler didn't mark the job
        # (signal-raised exceptions can bypass it), do it here.
        async def _ensure_failed() -> None:
            job = await repo.get(job_id)
            if job is not None and job.status not in ("completed", "failed"):
                stage = job.current_stage or "unknown"
                await repo.fail(
                    job_id, stage=stage,
                    error_type=type(exc).__name__, error_message=str(exc),
                )
                await push_dead_letter(job_id, type(exc).__name__, str(exc))

        asyncio.run(_ensure_failed())
        raise