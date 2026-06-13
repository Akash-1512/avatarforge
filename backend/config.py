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
    app_version: str = "2.0.0"
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
    azure_sora_deployment: str = "sora-2"  # Sora 2 scene-engine deployment name
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
    eval_report_path: str = "/data/eval/latest.json"
    azure_blob_connection_string: str = ""
    azure_blob_container: str = "avatarforge-media"

    # ── SadTalker (Phase 4) ──────────────────────────────
    sadtalker_checkpoint_dir: str = "/models/sadtalker"
    sadtalker_device: Literal["cpu", "cuda"] = "cpu"
    sadtalker_url: str = "http://sadtalker:8001"
    hunyuan_url: str = ""  # self-hosted GPU engine; e.g. RunPod TCP URL
    fal_api_key: str = ""  # managed engines (avatar + voice clone via fal)
    fal_avatar_model: str = "fal-ai/hunyuan-avatar"
    fal_voice_clone_model: str = "resemble-ai/chatterboxhd/text-to-speech"
    voice_clone_reference_url: str = ""  # public URL of the reference voice sample
    avatar_default_engine: str = "sadtalker"
    avatar_inference_timeout_sec: float = 2700.0

    # ── Observability (Phase 6) ─────────────────────────
    mlflow_tracking_uri: str = ""  # e.g. http://mlflow:5000; empty disables
    mlflow_experiment: str = "avatarforge"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ── API protection (Phase 7) ────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_default: str = "60/minute"
    rate_limit_generate: str = "5/minute"  # video jobs are expensive; throttle hard


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call this, never instantiate Settings directly."""
    return Settings()
