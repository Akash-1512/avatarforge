"""Script endpoint — dependency-overridden service, no network or DB."""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.models.schemas import ScriptResponse, ScriptSegment, TokenUsageInfo
from backend.services.llm.base import AllProvidersFailedError
from backend.services.llm.service import get_llm_service

FAKE_RESPONSE = ScriptResponse(
    title="Morning exercise",
    segments=[ScriptSegment(index=0, text="Hello.", est_duration_sec=5.0)],
    total_duration_sec=5.0,
    provider_used="azure_openai",
    model="gpt-4o-mini",
    latency_ms=420,
    usage=TokenUsageInfo(
        prompt_tokens=100,
        completion_tokens=200,
        total_tokens=300,
        estimated_cost_usd=0.000135,
    ),
)


class HappyService:
    async def generate_script(self, request):
        return FAKE_RESPONSE


class DownService:
    async def generate_script(self, request):
        raise AllProvidersFailedError("simulated total outage")


@pytest.fixture
def app():
    return create_app()


def test_generate_script_success(app):
    app.dependency_overrides[get_llm_service] = lambda: HappyService()
    client = TestClient(app)
    resp = client.post("/api/v1/script/generate", json={"topic": "Morning exercise benefits"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider_used"] == "azure_openai"
    assert body["usage"]["total_tokens"] == 300
    assert len(body["segments"]) == 1


def test_generate_script_validation(app):
    client = TestClient(app)
    resp = client.post("/api/v1/script/generate", json={"topic": "ab"})
    assert resp.status_code == 422

    resp = client.post(
        "/api/v1/script/generate",
        json={"topic": "valid topic here", "duration_seconds": 9999},
    )
    assert resp.status_code == 422


def test_generate_script_503_when_all_providers_down(app):
    app.dependency_overrides[get_llm_service] = lambda: DownService()
    client = TestClient(app)
    resp = client.post("/api/v1/script/generate", json={"topic": "Morning exercise benefits"})
    assert resp.status_code == 503
    assert "temporarily unavailable" in resp.json()["detail"]
