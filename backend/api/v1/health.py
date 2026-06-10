"""Liveness and deep health checks.

/health       — liveness probe (no dependencies touched)
/health/deep  — readiness probe (checks Redis + Postgres reachability)
"""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness — process is up and serving."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.environment,
    )


async def _check_redis() -> str:
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        return "ok"
    except Exception as exc:  # noqa: BLE001 — health checks report, never raise
        return f"unreachable: {type(exc).__name__}"


async def _check_postgres() -> str:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        settings = get_settings()
        engine = create_async_engine(settings.database_url, connect_args={"timeout": 2})
        async with engine.connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"unreachable: {type(exc).__name__}"


@router.get("/health/deep")
async def health_deep() -> Dict[str, Any]:
    """Readiness — verifies critical dependencies respond."""
    redis_status, pg_status = await asyncio.gather(_check_redis(), _check_postgres())
    deps = {"redis": redis_status, "postgres": pg_status}
    overall = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {"status": overall, "dependencies": deps}
