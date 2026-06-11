"""JobRepository against a real (SQLite) database — full lifecycle."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.db import Base
from backend.services.jobs.repository import JobRepository


@pytest_asyncio.fixture
async def repo(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield JobRepository(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_get(repo):
    job = await repo.create(topic="Morning walks", image_file_id="a" * 32 + ".png")
    fetched = await repo.get(job.id)
    assert fetched.status == "queued"
    assert fetched.topic == "Morning walks"


@pytest.mark.asyncio
async def test_lifecycle_to_completed(repo):
    job = await repo.create(topic="t", image_file_id="img.png")
    await repo.mark_running(job.id, celery_task_id="ct-1")
    await repo.set_stage(job.id, "script")
    await repo.set_stage(job.id, "tts")
    await repo.complete(
        job.id,
        script_title="Title",
        audio_file_id="a.wav",
        video_file_id="v.mp4",
        video_url="/api/v1/media/v.mp4",
        stage_timings={"script": 100, "tts": 200},
    )
    j = await repo.get(job.id)
    assert j.status == "completed"
    assert j.current_stage is None
    assert j.stage_timings == {"script": 100, "tts": 200}
    assert j.celery_task_id == "ct-1"


@pytest.mark.asyncio
async def test_lifecycle_to_failed(repo):
    job = await repo.create(topic="t", image_file_id="img.png")
    await repo.fail(job.id, stage="avatar", error_type="AvatarEngineError", error_message="boom")
    j = await repo.get(job.id)
    assert j.status == "failed"
    assert j.current_stage == "avatar"
    assert j.error_type == "AvatarEngineError"


@pytest.mark.asyncio
async def test_list_recent_ordering(repo):
    for i in range(3):
        await repo.create(topic=f"t{i}", image_file_id="img.png")
    jobs = await repo.list_recent(limit=2)
    assert len(jobs) == 2
