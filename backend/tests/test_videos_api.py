"""Videos API — submission, status, SSE; repo overridden, Celery mocked."""

import io
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import create_app
from backend.services.jobs.repository import get_job_repository


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (512, 512)).save(buf, format="PNG")
    return buf.getvalue()


def _job(status="queued", stage=None):
    return SimpleNamespace(
        id="j" * 32,
        status=status,
        current_stage=stage,
        topic="t",
        script_title=None,
        video_url=None,
        stage_timings={},
        error_type=None,
        error_message=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class FakeRepo:
    def __init__(self):
        self.jobs = {}
        self._sequence = None

    async def create(self, **fields):
        j = _job()
        self.jobs[j.id] = j
        return j

    async def get(self, job_id):
        if self._sequence:
            return self._sequence.pop(0) if self._sequence else None
        return self.jobs.get(job_id)

    async def list_recent(self, limit=20, offset=0):
        return list(self.jobs.values())[:limit]


@pytest.fixture
def app(monkeypatch):
    app = create_app()
    repo = FakeRepo()
    app.dependency_overrides[get_job_repository] = lambda: repo
    app.state.fake_repo = repo

    class FakeTask:
        @staticmethod
        def delay(job_id):
            app.state.enqueued = job_id

    monkeypatch.setattr("backend.workers.tasks.generate_video_task", FakeTask)
    return app


def test_submit_returns_202_and_enqueues(app):
    client = TestClient(app)
    resp = client.post(
        "/api/v1/videos/generate",
        files={"image": ("face.png", _png(), "image/png")},
        data={"topic": "Why morning walks improve focus"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert app.state.enqueued == body["job_id"]
    assert body["events_url"].endswith("/events")


def test_submit_rejects_bad_image(app):
    client = TestClient(app)
    resp = client.post(
        "/api/v1/videos/generate",
        files={"image": ("face.png", b"junk", "image/png")},
        data={"topic": "A valid topic here"},
    )
    assert resp.status_code == 422


def test_submit_rejects_bad_form(app):
    client = TestClient(app)
    resp = client.post(
        "/api/v1/videos/generate",
        files={"image": ("face.png", _png(), "image/png")},
        data={"topic": "ok topic", "duration_seconds": "9999"},
    )
    assert resp.status_code == 422


def test_job_status_and_404(app):
    client = TestClient(app)
    sub = client.post(
        "/api/v1/videos/generate",
        files={"image": ("face.png", _png(), "image/png")},
        data={"topic": "Another valid topic"},
    ).json()
    assert client.get(f"/api/v1/jobs/{sub['job_id']}").json()["status"] == "queued"
    assert client.get("/api/v1/jobs/" + "x" * 32).status_code == 404


def test_sse_streams_until_terminal(app):
    repo = app.state.fake_repo
    # 3 polls: running/script -> running/avatar -> completed (stream must close)
    seq = [
        _job("running", "script"),
        _job("running", "script"),
        _job("running", "avatar"),
        _job("completed", None),
    ]
    repo.jobs[seq[0].id] = seq[0]
    repo._sequence = list(seq)

    client = TestClient(app)
    with client.stream("GET", f"/api/v1/jobs/{seq[0].id}/events") as resp:
        assert resp.status_code == 200
        events = [line for line in resp.iter_lines() if line.startswith("data:")]
    # deduplicated transitions: script, avatar, completed
    assert len(events) == 3
    assert "completed" in events[-1]


def _fake_plan():
    from backend.models.schemas import VideoPlan

    return VideoPlan(
        topic="Compound interest for teens",
        tone="enthusiastic",
        duration_seconds=30,
        language="en",
        voice="casual_female",
        engine="sadtalker",
        rationale="teen audience",
    )


def test_plan_endpoint_returns_spec(app, monkeypatch):
    class FakePlanner:
        async def plan(self, brief):
            return _fake_plan()

    monkeypatch.setattr(
        "backend.services.planner.service.get_planner_service", lambda: FakePlanner()
    )
    client = TestClient(app)
    resp = client.post("/api/v1/videos/plan", json={"brief": "explain compound interest to teens"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tone"] == "enthusiastic"
    assert body["duration_seconds"] == 30
    assert body["voice"] == "casual_female"


def test_from_prompt_plans_and_enqueues(app, monkeypatch):
    class FakePlanner:
        async def plan(self, brief):
            return _fake_plan()

    monkeypatch.setattr(
        "backend.services.planner.service.get_planner_service", lambda: FakePlanner()
    )
    client = TestClient(app)
    resp = client.post(
        "/api/v1/videos/from-prompt",
        files={"image": ("face.png", _png(), "image/png")},
        data={"brief": "explain compound interest to teenagers, upbeat, 30s"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["plan"]["tone"] == "enthusiastic"
    assert app.state.enqueued  # task was queued
