"""Settings load with sane defaults and env overrides work."""

from backend.config import Settings


def test_default_settings_load() -> None:
    s = Settings(_env_file=None)
    assert s.environment == "dev"
    assert s.storage_backend == "local"
    assert s.llm_fallback_enabled is True


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.environment == "prod"
    assert s.log_level == "DEBUG"
