"""contentforge — AI content + film generation platform.

FastAPI application entrypoint. Uses the app factory pattern so tests
can spin up isolated instances with overridden settings.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

from backend.api.ratelimit import build_limiter
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
        title="contentforge API",
        description=(
            "AI avatar video generation — script, voice, and lip-sync pipeline.\n\n"
            "Typical flow: `POST /videos/generate` with a photo and topic, get a "
            "`job_id` back in milliseconds, then poll `GET /jobs/{id}` or stream "
            "`GET /jobs/{id}/events` (SSE) until the job completes with a `video_url`. "
            "See `docs/INTEGRATION.md` in the repo for the full contract."
        ),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {
                "name": "videos",
                "description": "Async video jobs — submit, track, stream progress.",
            },
            {
                "name": "script",
                "description": "LLM script generation (Azure OpenAI, OpenAI fallback).",
            },
            {
                "name": "tts",
                "description": "Speech synthesis (Azure Speech, OpenAI fallback).",
            },
            {
                "name": "avatar",
                "description": "Synchronous talking-head generation; prefer /videos/generate.",
            },
            {"name": "media", "description": "Generated file serving (WAV/MP4)."},
            {"name": "metrics", "description": "Operational metrics computed from audit tables."},
            {"name": "health", "description": "Liveness and dependency checks."},
        ],
    )

    # Rate limiting: per-IP, settings-driven, disabled in tests
    app.state.limiter = build_limiter()
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    # Operator console — a single static file served at the root. An explicit
    # route (not a StaticFiles mount at "/") so it never shadows /api, /docs,
    # or /redoc. The console is same-origin with the API, so CORS doesn't apply.
    from pathlib import Path

    from fastapi.responses import FileResponse, JSONResponse

    _ui_file = Path(__file__).parent / "frontend" / "index.html"

    @app.get("/", include_in_schema=False)
    async def operator_console() -> FileResponse:
        if not _ui_file.exists():
            return JSONResponse(  # type: ignore[return-value]
                {"detail": "Console not built", "api_docs": "/docs"}, status_code=404
            )
        return FileResponse(_ui_file)

    return app


app = create_app()
