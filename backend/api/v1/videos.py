"""Async video generation API — the product-facing surface of the pipeline.

POST /videos/generate validates inputs, persists the source image, creates
the job row, enqueues the Celery task, and returns 202 immediately. Progress
arrives via plain polling (GET /jobs/{id}) or SSE (GET /jobs/{id}/events).
"""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from backend.api.ratelimit import build_limiter
from backend.config import get_settings
from backend.services.avatar.validation import ImageValidationError, validate_source_image
from backend.services.jobs.repository import JobRepository, get_job_repository
from backend.services.storage.local import get_storage

router = APIRouter()

TERMINAL = {"completed", "failed"}


def _job_payload(job) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "current_stage": job.current_stage,
        "topic": job.topic,
        "script_title": job.script_title,
        "video_url": job.video_url,
        "stage_timings_ms": job.stage_timings or {},
        "error_type": job.error_type,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


_generate_limiter = build_limiter()


@router.post("/videos/generate", status_code=202)
@_generate_limiter.limit(lambda: get_settings().rate_limit_generate)
async def submit_video_job(
    request: Request,
    image: UploadFile = File(..., description="Front-facing photo, PNG/JPEG, min 256px"),
    topic: str = Form(..., min_length=3, max_length=500),
    tone: Literal["professional", "casual", "enthusiastic", "formal", "friendly"] = Form(
        "professional"
    ),
    duration_seconds: int = Form(60, ge=15, le=300),
    voice: Literal[
        "professional_female", "professional_male", "casual_female", "casual_male", "narrator"
    ] = Form("professional_female"),
    preprocess: Literal["crop", "resize", "full"] = Form("crop"),
    repo: JobRepository = Depends(get_job_repository),
) -> dict:
    """Queue a full video generation job. Returns a job_id immediately."""
    image_bytes = await image.read()
    try:
        ext = validate_source_image(image_bytes)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    stored_image = await get_storage().save_bytes(image_bytes, ext)
    job = await repo.create(
        topic=topic,
        tone=tone,
        duration_seconds=duration_seconds,
        voice=voice,
        image_file_id=stored_image.file_id,
        preprocess=preprocess,
    )

    from backend.workers.tasks import generate_video_task

    generate_video_task.delay(job.id)
    return {
        "job_id": job.id,
        "status": "queued",
        "status_url": f"/api/v1/jobs/{job.id}",
        "events_url": f"/api/v1/jobs/{job.id}/events",
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, repo: JobRepository = Depends(get_job_repository)) -> dict:
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_payload(job)


@router.get("/jobs")
async def list_jobs(
    limit: int = 20,
    offset: int = 0,
    repo: JobRepository = Depends(get_job_repository),
) -> dict:
    jobs = await repo.list_recent(limit=min(limit, 100), offset=offset)
    return {"jobs": [_job_payload(j) for j in jobs]}


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str, repo: JobRepository = Depends(get_job_repository)
) -> StreamingResponse:
    """Server-Sent Events stream of job progress; closes on terminal status."""
    if await repo.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def stream():
        last = None
        while True:
            job = await repo.get(job_id)
            if job is None:
                yield f"data: {json.dumps({'error': 'job disappeared'})}\n\n"
                return
            snapshot = (job.status, job.current_stage)
            if snapshot != last:
                yield f"data: {json.dumps(_job_payload(job))}\n\n"
                last = snapshot
            if job.status in TERMINAL:
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs-dlq")
async def dead_letter_queue(limit: int = 50) -> dict:
    """Inspect failed jobs awaiting attention."""
    try:
        import redis.asyncio as aioredis

        from backend.agents.pipeline import DLQ_KEY

        client = aioredis.from_url(get_settings().redis_url)
        entries = await client.lrange(DLQ_KEY, 0, min(limit, 200) - 1)
        await client.aclose()
        return {"entries": [json.loads(e) for e in entries]}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"DLQ unavailable: {exc}") from exc
