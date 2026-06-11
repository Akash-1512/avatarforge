"""LangGraph pipeline — fake services, real graph execution, real SQLite repo."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.agents.nodes import PipelineNodes
from backend.agents.pipeline import build_graph, run_pipeline
from backend.agents.state import VideoPipelineState
from backend.models.db import Base
from backend.models.schemas import (
    AvatarResponse,
    ScriptResponse,
    ScriptSegment,
    TokenUsageInfo,
    TTSResponse,
)
from backend.services.jobs.repository import JobRepository

SCRIPT = ScriptResponse(
    title="Walking",
    segments=[ScriptSegment(index=0, text="Hello there.", est_duration_sec=5)],
    total_duration_sec=5,
    provider_used="azure_openai",
    model="gpt-4.1-mini",
    latency_ms=10,
    usage=TokenUsageInfo(
        prompt_tokens=1, completion_tokens=1, total_tokens=2, estimated_cost_usd=0.0
    ),
)
TTS = TTSResponse(
    audio_url="/api/v1/media/aa.wav",
    file_id="a" * 32 + ".wav",
    provider_used="azure_speech",
    model="neerja",
    voice="professional_female",
    characters=12,
    audio_duration_sec=5.0,
    latency_ms=10,
    estimated_cost_usd=0.0,
    format="wav",
)
AVATAR = AvatarResponse(
    video_url="/api/v1/media/vv.mp4",
    file_id="b" * 32 + ".mp4",
    video_duration_sec=5.0,
    width=256,
    height=256,
    codec="h264",
    latency_ms=10,
    preprocess="crop",
    enhancer=False,
)


class FakeLLM:
    async def generate_script(self, req):
        return SCRIPT


class FakeTTS:
    async def synthesize(self, req):
        return TTS


class FakeAvatar:
    async def generate(self, image_bytes, audio_file_id, **kw):
        return AVATAR


class FlakyTTS:
    """Fails once with a transient outage, then succeeds — exercises RetryPolicy."""

    def __init__(self):
        self.calls = 0

    async def synthesize(self, req):
        self.calls += 1
        if self.calls == 1:
            from backend.services.tts.base import AllTTSProvidersFailedError

            raise AllTTSProvidersFailedError("transient full outage")
        return TTS


class BrokenAvatar:
    async def generate(self, *a, **k):
        raise RuntimeError("engine down hard")


class FakeStorage:
    def __init__(self, tmp_path):
        self.img = tmp_path / ("c" * 32 + ".png")
        self.img.write_bytes(b"fakepng")

    def resolve_path(self, file_id):
        return str(self.img) if file_id == self.img.name else None


@pytest_asyncio.fixture
async def repo(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/p.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield JobRepository(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


def _nodes(repo, tmp_path, tts=None, avatar=None):
    return PipelineNodes(
        llm_service=FakeLLM(),
        tts_service=tts or FakeTTS(),
        avatar_service=avatar or FakeAvatar(),
        storage=FakeStorage(tmp_path),
        repo=repo,
    )


async def _make_job(repo):
    return await repo.create(topic="Why walking helps focus", image_file_id="c" * 32 + ".png")


@pytest.mark.asyncio
async def test_happy_path_completes_job(repo, tmp_path):
    job = await _make_job(repo)
    result = await run_pipeline(job.id, _nodes(repo, tmp_path), repo)
    assert result["status"] == "completed"
    j = await repo.get(job.id)
    assert j.status == "completed"
    assert j.script_title == "Walking"
    assert j.video_url == "/api/v1/media/vv.mp4"
    assert set(j.stage_timings) == {"script", "tts", "avatar"}


@pytest.mark.asyncio
async def test_node_retry_policy_recovers_transient_failure(repo, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.agents.pipeline.push_dead_letter", _noop_dlq)
    job = await _make_job(repo)
    flaky = FlakyTTS()
    result = await run_pipeline(job.id, _nodes(repo, tmp_path, tts=flaky), repo)
    assert result["status"] == "completed"
    assert flaky.calls == 2  # failed once, retried by RetryPolicy, succeeded


async def _noop_dlq(*a, **k):
    return None


@pytest.mark.asyncio
async def test_terminal_failure_marks_job_and_dead_letters(repo, tmp_path, monkeypatch):
    pushed = []

    async def capture_dlq(job_id, error_type, error_message):
        pushed.append((job_id, error_type))

    monkeypatch.setattr("backend.agents.pipeline.push_dead_letter", capture_dlq)
    job = await _make_job(repo)
    with pytest.raises(RuntimeError):
        await run_pipeline(job.id, _nodes(repo, tmp_path, avatar=BrokenAvatar()), repo)
    j = await repo.get(job.id)
    assert j.status == "failed"
    assert j.current_stage == "avatar"
    assert pushed == [(job.id, "RuntimeError")]


@pytest.mark.asyncio
async def test_graph_topology():
    g = build_graph(PipelineNodes(None, None, None, None, None))
    drawn = g.get_graph()
    names = set(drawn.nodes)
    assert {"script", "tts", "avatar", "store", "notify"} <= names


@pytest.mark.asyncio
async def test_state_validates():
    s = VideoPipelineState(job_id="j1", topic="t", image_file_id="i.png")
    assert s.stage_timings == {}


class BuggyTTS:
    def __init__(self):
        self.calls = 0

    async def synthesize(self, req):
        self.calls += 1
        raise ValueError("logic bug — must not be retried")


@pytest.mark.asyncio
async def test_logic_errors_are_not_retried(repo, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.agents.pipeline.push_dead_letter", _noop_dlq)
    job = await _make_job(repo)
    buggy = BuggyTTS()
    with pytest.raises(ValueError):
        await run_pipeline(job.id, _nodes(repo, tmp_path, tts=buggy), repo)
    assert buggy.calls == 1  # no retry on non-transient errors
