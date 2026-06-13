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
    task_acks_late=True,  # don't ack until done — a lost worker won't drop the job
    # ...but a long, expensive, non-idempotent render must NOT be silently
    # replayed if the worker restarts mid-flight: that re-submits to the engine
    # and resets the clock. Reject-on-lost marks it failed instead, so the
    # pipeline's own failure path + DLQ handle a retry deliberately.
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=1,  # video jobs are heavy — one at a time
    # The task limits MUST exceed the avatar inference timeout, or Celery kills
    # a render that the engine would have completed. Inference can take ~8 min
    # (managed fal) to far longer (self-host GPU), so derive from the setting
    # with headroom for the script + TTS + packaging stages around it.
    task_soft_time_limit=int(settings.avatar_inference_timeout_sec) + 300,
    task_time_limit=int(settings.avatar_inference_timeout_sec) + 600,
)
