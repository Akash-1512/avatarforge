"""Celery application — broker and result backend on Redis.

Workers run as a separate container (see docker-compose.yml).
Tasks live in backend/workers/tasks.py and are auto-discovered.
"""

from celery import Celery

from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "avatarforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # re-queue on worker crash
    worker_prefetch_multiplier=1,  # video jobs are heavy — one at a time
    task_soft_time_limit=600,  # 10 min soft kill for runaway jobs
    task_time_limit=900,
)
