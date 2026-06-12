"""Rate limiting — 429 after the per-IP budget on the expensive endpoint."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import get_settings


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (512, 512)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def limited_app(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_GENERATE", "3/minute")
    get_settings.cache_clear()
    # Import AFTER env is set so module-level limiter picks it up
    import importlib

    import backend.api.ratelimit as rl
    import backend.api.v1.router as router_mod
    import backend.api.v1.videos as videos
    import backend.main as main_mod

    importlib.reload(rl)
    importlib.reload(videos)
    importlib.reload(router_mod)
    importlib.reload(main_mod)

    from backend.services.jobs.repository import get_job_repository

    app = main_mod.create_app()

    class Repo:
        async def create(self, **fields):
            from types import SimpleNamespace

            return SimpleNamespace(id="r" * 32)

    app.dependency_overrides[get_job_repository] = lambda: Repo()

    class FakeTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr("backend.workers.tasks.generate_video_task", FakeTask)
    yield app
    get_settings.cache_clear()


def test_429_after_budget_exhausted(limited_app):
    client = TestClient(limited_app)
    statuses = []
    for _ in range(5):
        resp = client.post(
            "/api/v1/videos/generate",
            files={"image": ("face.png", _png(), "image/png")},
            data={"topic": "Rate limit verification topic"},
        )
        statuses.append(resp.status_code)
    assert statuses[:3] == [202, 202, 202]
    assert statuses[3] == 429
    assert statuses[4] == 429
