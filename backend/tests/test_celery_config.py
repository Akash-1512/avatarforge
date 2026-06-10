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
