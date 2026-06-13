"""Per-job trace: correlation id flows into audit rows; trace assembles stages."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.avatar_usage import AvatarUsage
from backend.models.db import Base
from backend.models.job import VideoJob
from backend.models.tts_usage import TTSUsage
from backend.models.usage import TokenUsage
from backend.observability.trace_context import get_job_id, set_job_id
from backend.services.trace.service import build_trace


@pytest_asyncio.fixture
async def sf(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def test_context_var_roundtrip():
    set_job_id("abc123")
    assert get_job_id() == "abc123"
    set_job_id(None)
    assert get_job_id() is None


@pytest.mark.asyncio
async def test_trace_assembles_stages_with_fallback(sf):
    jid = "j" * 32
    async with sf() as s:
        s.add(
            VideoJob(
                id=jid,
                topic="t",
                image_file_id="i",
                status="completed",
                engine="fal",
                language="en",
                script_title="T",
                stage_timings={},
            )
        )
        # LLM: primary failed, fallback (openai) succeeded -> fell_back True, 2 attempts
        s.add(
            TokenUsage(
                job_id=jid,
                provider="azure_openai",
                model="m",
                success=False,
                total_tokens=0,
                estimated_cost_usd=0.0,
                latency_ms=120,
            )
        )
        s.add(
            TokenUsage(
                job_id=jid,
                provider="openai",
                model="m",
                success=True,
                prompt_tokens=300,
                completion_tokens=120,
                total_tokens=420,
                estimated_cost_usd=0.0006,
                latency_ms=890,
            )
        )
        s.add(
            TTSUsage(
                job_id=jid,
                provider="azure_speech",
                model="m",
                voice_preset="v",
                characters=140,
                estimated_cost_usd=0.0,
                latency_ms=1500,
                success=True,
            )
        )
        s.add(
            AvatarUsage(
                job_id=jid,
                audio_file_id="a",
                engine="fal",
                video_duration_sec=5.0,
                latency_ms=138000,
                success=True,
            )
        )
        await s.commit()

    trace = await build_trace(jid, sf)
    assert trace["found"] is True
    stages = {st["stage"]: st for st in trace["stages"]}
    assert stages["script"]["provider"] == "openai"
    assert stages["script"]["fell_back"] is True
    assert stages["script"]["attempts"] == 2
    assert stages["script"]["total_tokens"] == 420
    assert stages["tts"]["provider"] == "azure_speech"
    assert stages["avatar"]["provider"] == "fal"
    # latency percentages sum to ~100
    assert abs(sum(st["latency_pct"] for st in trace["stages"]) - 100) < 1.0


@pytest.mark.asyncio
async def test_trace_missing_job(sf):
    assert (await build_trace("nope", sf))["found"] is False
