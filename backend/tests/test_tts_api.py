"""TTS + media endpoints — dependency overrides, no network."""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.models.schemas import TTSResponse
from backend.services.tts.base import AllTTSProvidersFailedError
from backend.services.tts.service import get_tts_service

FAKE = TTSResponse(
    audio_url="/api/v1/media/" + "a" * 32 + ".wav",
    file_id="a" * 32 + ".wav",
    provider_used="azure_speech",
    model="en-IN-NeerjaNeural",
    voice="professional_female",
    characters=42,
    audio_duration_sec=3.5,
    latency_ms=800,
    estimated_cost_usd=0.0,
    format="wav 16kHz mono (SadTalker-ready)",
)


class HappyTTS:
    async def synthesize(self, request):
        return FAKE


class DownTTS:
    async def synthesize(self, request):
        raise AllTTSProvidersFailedError("simulated")


@pytest.fixture
def app():
    return create_app()


def test_voices_listed(app):
    client = TestClient(app)
    resp = client.get("/api/v1/tts/voices")
    assert resp.status_code == 200
    body = resp.json()
    assert "professional_female" in body
    assert body["professional_female"]["azure_voice"] == "en-IN-NeerjaNeural"


def test_synthesize_success(app):
    app.dependency_overrides[get_tts_service] = lambda: HappyTTS()
    resp = TestClient(app).post("/api/v1/tts/synthesize", json={"text": "Hello world"})
    assert resp.status_code == 200
    assert resp.json()["provider_used"] == "azure_speech"


def test_synthesize_validation(app):
    client = TestClient(app)
    assert client.post("/api/v1/tts/synthesize", json={"text": ""}).status_code == 422
    assert (
        client.post(
            "/api/v1/tts/synthesize", json={"text": "hi", "voice": "robot_voice"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v1/tts/synthesize", json={"text": "hi", "speaking_rate": 5.0}).status_code
        == 422
    )


def test_synthesize_503_when_down(app):
    app.dependency_overrides[get_tts_service] = lambda: DownTTS()
    resp = TestClient(app).post("/api/v1/tts/synthesize", json={"text": "Hello"})
    assert resp.status_code == 503


def test_media_404_and_traversal_guard(app):
    client = TestClient(app)
    assert client.get("/api/v1/media/" + "0" * 32 + ".wav").status_code == 404
    assert client.get("/api/v1/media/..%2F..%2Fetc%2Fpasswd").status_code == 404
