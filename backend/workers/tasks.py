"""Celery tasks.

Phase 1 ships a single smoke-test task so the worker container,
broker, and Flower dashboard can all be verified end to end.
The real generate_video_task lands in Phase 5.
"""

import time

from backend.workers.celery_app import celery_app


@celery_app.task(name="avatarforge.ping")
def ping(payload: str = "pong") -> dict:
    """Smoke test — verifies broker round-trip and result backend."""
    time.sleep(1)
    return {"echo": payload, "worker": "alive"}
