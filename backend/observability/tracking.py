"""MLflow instrumentation — one parent run per job, nested runs per stage.

Hard rule: observability must never break the pipeline. Every MLflow call
is wrapped; if the tracking server is down or unconfigured, the pipeline
runs identically and a single warning is logged.
"""

from typing import Optional

from backend.config import get_settings
from backend.observability.logging import get_logger

logger = get_logger(__name__)


def enabled() -> bool:
    return bool(get_settings().mlflow_tracking_uri)


def _client():
    import mlflow

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    return mlflow


def log_job_run(
    job_id: str,
    *,
    status: str,
    topic: str,
    stage_timings: dict,
    llm_provider: Optional[str] = None,
    tts_provider: Optional[str] = None,
    video_duration_sec: float = 0.0,
    error_type: Optional[str] = None,
) -> None:
    """Record a completed/failed job as a parent run with per-stage child runs."""
    if not enabled():
        return
    try:
        mlflow = _client()
        with mlflow.start_run(run_name=f"job-{job_id[:8]}") as parent:
            mlflow.set_tags(
                {
                    "job_id": job_id,
                    "status": status,
                    "llm_provider": llm_provider or "n/a",
                    "tts_provider": tts_provider or "n/a",
                    **({"error_type": error_type} if error_type else {}),
                }
            )
            mlflow.log_param("topic", topic[:250])
            total_ms = sum(stage_timings.values())
            mlflow.log_metric("total_ms", total_ms)
            mlflow.log_metric("video_duration_sec", video_duration_sec)
            for stage, ms in stage_timings.items():
                mlflow.log_metric(f"{stage}_ms", ms)
                with mlflow.start_run(run_name=stage, nested=True):
                    mlflow.set_tag("job_id", job_id)
                    mlflow.log_metric("latency_ms", ms)
            logger.info("mlflow_job_logged", job_id=job_id, run_id=parent.info.run_id)
    except Exception as exc:  # noqa: BLE001 — observability is best-effort
        logger.warning("mlflow_logging_failed", job_id=job_id, error=str(exc)[:200])
