"""Async SQLAlchemy engine and session factory.

Tables are created on startup in dev (metadata.create_all). Alembic
migrations take over in Phase 5 when the job-history models land.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def reset_engine() -> None:
    """Dispose the current engine and clear cached factory.

    asyncpg pools are bound to the event loop that created them. A Celery task
    running under a fresh loop (asyncio.run per task) must not reuse a pool from
    a prior loop, or queries raise "Future attached to a different loop". Calling
    this at task entry forces a new engine + session factory bound to this loop.
    """
    global _engine, _session_factory
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception:  # noqa: BLE001 — best-effort teardown of a stale pool
            pass
    _engine = None
    _session_factory = None


async def init_db() -> None:
    """Create tables in dev. Safe to call repeatedly."""
    from backend.models import (  # noqa: F401 — register models
        avatar_usage,
        chat,
        job,
        memory,
        tts_usage,
        usage,
    )

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session
