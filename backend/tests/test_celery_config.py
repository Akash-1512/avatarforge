"""Celery app wiring — config sanity, no broker needed."""

from backend.workers.celery_app import celery_app
from backend.workers.tasks import ping


def test_celery_app_configured() -> None:
    assert celery_app.main == "avatarforge"
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_ping_task_registered() -> None:
    assert "avatarforge.ping" in celery_app.tasks


def test_ping_task_runs_synchronously() -> None:
    """Run the task body directly (no broker) — verifies logic."""
    result = ping.run("hello")
    assert result == {"echo": "hello", "worker": "alive"}


def test_task_limits_exceed_inference_timeout():
    """Regression: Celery must not kill a render the engine would finish.
    soft/hard task limits must sit above the avatar inference timeout."""
    from backend.config import get_settings
    from backend.workers.celery_app import celery_app

    inf = get_settings().avatar_inference_timeout_sec
    assert celery_app.conf.task_soft_time_limit > inf
    assert celery_app.conf.task_time_limit > celery_app.conf.task_soft_time_limit
