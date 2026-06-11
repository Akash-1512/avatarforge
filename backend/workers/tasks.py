"""Celery tasks.

avatarforge.generate_video wraps the full LangGraph pipeline. The worker
runs with prefetch=1 and acks_late, so a crashed worker re-queues the job.
The smoke-test ping task from Phase 1 remains for diagnostics.
"""

import asyncio
import time

from backend.workers.celery_app import celery_app


@celery_app.task(name="avatarforge.ping")
def ping(payload: str = "pong") -> dict:
    """Smoke test — verifies broker round-trip and result backend."""
    time.sleep(1)
    return {"echo": payload, "worker": "alive"}


@celery_app.task(name="avatarforge.generate_video", bind=True)
def generate_video_task(self, job_id: str) -> dict:
    """Execute the full video pipeline for a queued job."""
    from backend.agents.pipeline import get_default_nodes, run_pipeline
    from backend.services.jobs.repository import get_job_repository

    repo = get_job_repository()

    async def _run() -> dict:
        await repo.mark_running(job_id, celery_task_id=self.request.id)
        return await run_pipeline(job_id, get_default_nodes(), repo)

    return asyncio.run(_run())
