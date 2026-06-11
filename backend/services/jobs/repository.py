"""Async CRUD for video jobs.

A thin repository class with an injectable session factory so tests run
against SQLite while production uses Postgres unchanged.
"""

import uuid
from functools import lru_cache
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.models.job import VideoJob

TERMINAL_STATUSES = {"completed", "failed"}


class JobRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def create(self, **fields) -> VideoJob:
        job = VideoJob(id=uuid.uuid4().hex, **fields)
        async with self._sf() as s:
            s.add(job)
            await s.commit()
            await s.refresh(job)
        return job

    async def get(self, job_id: str) -> Optional[VideoJob]:
        async with self._sf() as s:
            return await s.get(VideoJob, job_id)

    async def list_recent(self, limit: int = 20, offset: int = 0) -> Sequence[VideoJob]:
        async with self._sf() as s:
            rows = await s.execute(
                select(VideoJob).order_by(VideoJob.created_at.desc()).limit(limit).offset(offset)
            )
            return rows.scalars().all()

    async def _update(self, job_id: str, **fields) -> None:
        async with self._sf() as s:
            job = await s.get(VideoJob, job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            await s.commit()

    async def mark_running(self, job_id: str, celery_task_id: str | None = None) -> None:
        await self._update(job_id, status="running", celery_task_id=celery_task_id)

    async def set_stage(self, job_id: str, stage: str) -> None:
        await self._update(job_id, current_stage=stage)

    async def complete(self, job_id: str, **output_fields) -> None:
        await self._update(job_id, status="completed", current_stage=None, **output_fields)

    async def fail(
        self,
        job_id: str,
        stage: str,
        error_type: str,
        error_message: str,
        stage_timings: dict | None = None,
    ) -> None:
        await self._update(
            job_id,
            status="failed",
            current_stage=stage,
            error_type=error_type,
            error_message=error_message[:2000],
            **({"stage_timings": stage_timings} if stage_timings else {}),
        )


@lru_cache
def get_job_repository() -> JobRepository:
    from backend.models.db import get_session_factory

    return JobRepository(get_session_factory())
