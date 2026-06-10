"""avatarforge — AI avatar video generation platform.

FastAPI application entrypoint. Uses the app factory pattern so tests
can spin up isolated instances with overridden settings.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.router import api_router
from backend.config import get_settings
from backend.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hooks."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "avatarforge_starting",
        env=settings.environment,
        version=settings.app_version,
    )
    try:
        from backend.models.db import init_db

        await init_db()
        logger.info("db_tables_ready")
    except Exception as exc:  # noqa: BLE001 — app must boot even if DB is down
        logger.warning("db_init_skipped", error=str(exc)[:200])
    yield
    logger.info("avatarforge_shutdown")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title="avatarforge API",
        description="AI avatar video generation — script, voice, and lip-sync pipeline",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
