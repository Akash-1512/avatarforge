"""Metrics summary — real SQLite with seeded audit rows."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.avatar_usage import AvatarUsage
from backend.models.db import Base
from backend.models.tts_usage import TTSUsage
from backend.models.usage import TokenUsage
from backend.services.metrics.summary import compute_summary


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/m.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        s.add_all(
            [
                TokenUsage(
                    provider="azure_openai",
                    model="gpt-4.1-mini",
                    operation="generate_script",
                    prompt_tokens=100,
                    completion_tokens=200,
                    total_tokens=300,
                    estimated_cost_usd=0.001,
                    latency_ms=900,
                    success=True,
                ),
                TokenUsage(
                    provider="azure_openai",
                    model="gpt-4.1-mini",
                    operation="generate_script",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    estimated_cost_usd=0.0,
                    latency_ms=100,
                    success=False,
                    error_type="RateLimit",
                ),
                TokenUsage(
                    provider="openai",
                    model="gpt-4o-mini",
                    operation="generate_script",
                    prompt_tokens=100,
                    completion_tokens=150,
                    total_tokens=250,
                    estimated_cost_usd=0.002,
                    latency_ms=1200,
                    success=True,
                ),
                TTSUsage(
                    provider="azure_speech",
                    model="neerja",
                    voice_preset="professional_female",
                    characters=100,
                    estimated_cost_usd=0.0,
                    audio_duration_sec=9.0,
                    latency_ms=800,
                    success=True,
                ),
                AvatarUsage(
                    audio_file_id="a.wav",
                    preprocess="crop",
                    enhancer=False,
                    video_duration_sec=4.8,
                    latency_ms=884100,
                    success=True,
                ),
            ]
        )
        await s.commit()
    yield sf
    await engine.dispose()


@pytest.mark.asyncio
async def test_summary_computes_rates_and_fallback(session_factory):
    out = await compute_summary(session_factory)
    azure = out["llm_providers"]["azure_openai"]
    assert azure["calls"] == 2 and azure["success_rate"] == 0.5
    assert out["llm_providers"]["openai"]["success_rate"] == 1.0
    # 2 successful LLM calls total, 1 from non-primary openai -> 0.5 fallback rate
    assert out["llm_fallback_rate"] == 0.5
    assert out["avatar"]["calls"] == 1
    assert out["total_cost_usd"] == 0.003
