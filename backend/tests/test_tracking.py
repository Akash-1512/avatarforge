"""Observability must be a no-op when unconfigured and never raise."""

from backend.observability import lf, tracking


def test_tracking_disabled_without_uri(monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    from backend.config import get_settings

    get_settings.cache_clear()
    assert tracking.enabled() is False
    # Must be a silent no-op, not an exception
    tracking.log_job_run("j1", status="completed", topic="t", stage_timings={"script": 10})
    get_settings.cache_clear()


def test_langfuse_noop_without_keys():
    lf._get_client.cache_clear()
    lf.record_generation(
        name="generate_script",
        model="m",
        provider="p",
        input_text="i",
        output_text="o",
        prompt_tokens=1,
        completion_tokens=1,
        latency_ms=10,
        success=True,
    )  # no exception = pass
    lf._get_client.cache_clear()
