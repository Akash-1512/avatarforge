"""Regression: asyncpg loop-binding fix.

A Celery task runs each job under a fresh event loop. asyncpg pools are
loop-bound, so the engine must be reset per task and consumers must resolve
the session factory lazily — otherwise a cached factory from a dead loop
raises "Future attached to a different loop" and jobs never complete.
"""

import pytest

import backend.models.db as db
from backend.services.jobs.repository import JobRepository


@pytest.mark.asyncio
async def test_reset_engine_clears_globals(monkeypatch):
    # Point at an in-memory sqlite so get_engine() actually builds something.
    monkeypatch.setattr(
        db.get_settings(), "database_url", "sqlite+aiosqlite:///:memory:", raising=False
    )
    db._engine = None
    db._session_factory = None
    eng = db.get_engine()
    assert db._engine is eng
    db.get_session_factory()
    assert db._session_factory is not None

    await db.reset_engine()
    assert db._engine is None
    assert db._session_factory is None


def test_lazy_repo_resolves_factory_each_call(monkeypatch):
    """A repo with no injected factory reads the *current* global factory,
    so an engine reset between calls is honoured rather than captured once."""
    calls = {"n": 0}

    def fake_factory():
        calls["n"] += 1
        return "factory-%d" % calls["n"]

    monkeypatch.setattr(db, "get_session_factory", fake_factory)
    repo = JobRepository()  # no injected factory
    assert repo._sf == "factory-1"
    assert repo._sf == "factory-2"  # resolved again, not cached


def test_injected_factory_still_wins():
    """Tests inject a SQLite factory explicitly — that path is unchanged."""
    sentinel = object()
    repo = JobRepository(session_factory=sentinel)
    assert repo._sf is sentinel
