"""Centralised configuration via pydantic-settings.

Every tunable lives here and maps 1:1 to a variable in .env.example.
Services never read os.environ directly — they take Settings.
"""

from functools import lru_cache
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_version: str = "0.1.0"
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    cors_origins: List[str] = ["http://localhost:3000"]

    # ── Database ─────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://avatarforge:avatarforge@postgres:5432/avatarforge"

    # ── Redis / Celery ───────────────────────────────────
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ── LLM providers (Phase 2) ──────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-10-21"
    openai_api_key: str = ""
    llm_fallback_enabled: bool = True

    # ── TTS providers (Phase 3) ──────────────────────────
    azure_speech_key: str = ""
    azure_speech_region: str = "centralindia"
    tts_default_voice: str = "en-IN-NeerjaNeural"

    # ── Storage (Phase 3+) ───────────────────────────────
    storage_backend: Literal["local", "azure_blob"] = "local"
    local_storage_path: str = "/data/media"
    azure_blob_connection_string: str = ""
    azure_blob_container: str = "avatarforge-media"

    # ── SadTalker (Phase 4) ──────────────────────────────
    sadtalker_checkpoint_dir: str = "/models/sadtalker"
    sadtalker_device: Literal["cpu", "cuda"] = "cpu"
    sadtalker_url: str = "http://sadtalker:8001"
    avatar_inference_timeout_sec: float = 1800.0


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call this, never instantiate Settings directly."""
    return Settings()
