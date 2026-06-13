"""Studio chat + memory API — wiring, thread continuity, preference controls."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.v1.studio as studio
from backend.main import create_app
from backend.models.db import Base
from backend.models.schemas import VideoPlan
from backend.services.memory.service import MemoryService


@pytest_asyncio.fixture
async def wired(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/s.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    mem = MemoryService(session_factory=sf)
    monkeypatch.setattr(studio, "get_memory_service", lambda: mem)

    class FakePlanner:
        async def chat(self, message, history=None, memory_hint=""):
            # echo the hint back so the test can assert memory was applied
            return VideoPlan(
                topic=message[:100] if len(message) >= 3 else "untitled",
                tone="casual",
                duration_seconds=30,
                language="hi",
                rationale=f"hint:{memory_hint}",
            )

    monkeypatch.setattr(studio, "get_planner_service", lambda: FakePlanner())
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_creates_thread_and_persists_history(wired):
    c = TestClient(create_app())
    r = c.post("/api/v1/studio/chat", json={"user_id": "u1", "message": "make a 30s hype video"})
    assert r.status_code == 200
    body = r.json()
    tid = body["thread_id"]
    assert len(body["history"]) == 2  # user + assistant
    # second turn on the same thread accumulates history
    r2 = c.post(
        "/api/v1/studio/chat", json={"user_id": "u1", "message": "more energetic", "thread_id": tid}
    )
    assert len(r2.json()["history"]) == 4


@pytest.mark.asyncio
async def test_chat_learns_then_applies_memory(wired):
    c = TestClient(create_app())
    c.post("/api/v1/studio/chat", json={"user_id": "u2", "message": "hindi hype video"})
    # the plan learned tone/language/duration; a new thread should recall them
    r = c.post("/api/v1/studio/chat", json={"user_id": "u2", "message": "another one"})
    assert "hi" in r.json()["memory_applied"]  # language recalled into the hint


@pytest.mark.asyncio
async def test_memory_view_and_delete(wired):
    c = TestClient(create_app())
    c.post("/api/v1/studio/chat", json={"user_id": "u3", "message": "casual short video"})
    view = c.get("/api/v1/studio/memory/u3").json()
    assert view["preferences"]["memory_enabled"] is True
    assert len(view["memories"]) >= 1
    mid = view["memories"][0]["id"]
    assert c.delete(f"/api/v1/studio/memory/u3/{mid}").status_code == 200
    assert c.delete("/api/v1/studio/memory/u3/999999").status_code == 404


@pytest.mark.asyncio
async def test_set_preferences_and_disable_memory(wired):
    c = TestClient(create_app())
    r = c.put(
        "/api/v1/studio/preferences/u4", json={"default_tone": "formal", "memory_enabled": False}
    )
    assert r.json()["preferences"]["default_tone"] == "formal"
    assert r.json()["preferences"]["memory_enabled"] is False
    # with memory off, a chat learns nothing
    c.post("/api/v1/studio/chat", json={"user_id": "u4", "message": "a video"})
    assert c.get("/api/v1/studio/memory/u4").json()["memories"] == []
