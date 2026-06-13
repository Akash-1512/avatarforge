"""Memory service + studio chat: short-term thread, long-term memory, controls."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.db import Base
from backend.services.memory.service import MemoryService


@pytest_asyncio.fixture
async def mem(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/m.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield MemoryService(session_factory=async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


@pytest.mark.asyncio
async def test_thread_is_ordered_short_term_memory(mem):
    await mem.append_message("t1", "u1", "user", "make a 30s intro")
    await mem.append_message("t1", "u1", "assistant", "ok, professional, 30s")
    await mem.append_message("t1", "u1", "user", "more energetic")
    hist = await mem.load_thread("t1")
    assert [m["role"] for m in hist] == ["user", "assistant", "user"]
    assert hist[0]["content"] == "make a 30s intro"


@pytest.mark.asyncio
async def test_threads_are_isolated(mem):
    await mem.append_message("t1", "u1", "user", "thread one")
    await mem.append_message("t2", "u1", "user", "thread two")
    assert len(await mem.load_thread("t1")) == 1
    assert (await mem.load_thread("t2"))[0]["content"] == "thread two"


@pytest.mark.asyncio
async def test_remember_keeps_one_active_value_per_kind(mem):
    await mem.remember("u1", "language", "en", "first brief")
    await mem.remember("u1", "language", "hi", "second brief")
    recalled = await mem.recall("u1")
    langs = [m for m in recalled if m["kind"] == "language"]
    assert len(langs) == 1 and langs[0]["value"] == "hi"  # latest wins, prior deactivated


@pytest.mark.asyncio
async def test_memory_disabled_blocks_recall_and_learning(mem):
    await mem.set_preferences("u1", memory_enabled=False)
    await mem.remember("u1", "tone", "casual", "brief")  # should be a no-op
    assert await mem.recall("u1") == []


@pytest.mark.asyncio
async def test_memories_are_per_user(mem):
    await mem.remember("u1", "tone", "formal", "b")
    await mem.remember("u2", "tone", "casual", "b")
    u1 = {m["value"] for m in await mem.recall("u1")}
    u2 = {m["value"] for m in await mem.recall("u2")}
    assert "formal" in u1 and "formal" not in u2
    assert "casual" in u2 and "casual" not in u1


@pytest.mark.asyncio
async def test_delete_one_and_clear_all(mem):
    await mem.remember("u1", "tone", "formal", "b")
    await mem.remember("u1", "language", "hi", "b")
    recalled = await mem.recall("u1")
    target = recalled[0]["id"]
    assert await mem.delete_memory("u1", target) is True
    assert await mem.delete_memory("u2", target) is False  # wrong owner
    n = await mem.clear_memories("u1")
    assert n >= 1
    assert await mem.recall("u1") == []


@pytest.mark.asyncio
async def test_preferences_validation_rejects_bad_values(mem):
    p = await mem.set_preferences(
        "u1", default_tone="dramatic", default_duration=9999, default_language="hi"
    )
    assert p.default_tone is None  # "dramatic" not in allowed set
    assert p.default_duration is None  # out of 15..300
    assert p.default_language == "hi"  # valid


@pytest.mark.asyncio
async def test_extract_from_plan_learns_settings(mem):
    class P:
        tone = "enthusiastic"
        language = "hi"
        duration_seconds = 30

    await mem.extract_from_plan("u1", P(), "hype video in hindi")
    kinds = {m["kind"]: m["value"] for m in await mem.recall("u1")}
    assert kinds == {"tone": "enthusiastic", "language": "hi", "duration": "30"}
