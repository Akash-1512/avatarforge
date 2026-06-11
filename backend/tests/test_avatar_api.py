"""Avatar endpoint — dependency-overridden service."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import create_app
from backend.models.schemas import AvatarResponse
from backend.services.avatar.client import AvatarEngineError
from backend.services.avatar.service import get_avatar_service
from backend.services.avatar.validation import ImageValidationError

FAKE = AvatarResponse(
    video_url="/api/v1/media/" + "b" * 32 + ".mp4",
    file_id="b" * 32 + ".mp4",
    video_duration_sec=9.1,
    width=256,
    height=256,
    codec="h264",
    latency_ms=180000,
    preprocess="crop",
    enhancer=False,
)


def _png(size=(512, 512)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size).save(buf, format="PNG")
    return buf.getvalue()


class HappyAvatar:
    class client:  # noqa: N801
        @staticmethod
        async def health():
            return {"status": "ok", "checkpoints_present": True}

    async def generate(self, image_bytes, audio_file_id, **kwargs):
        return FAKE


class ValidationFailAvatar(HappyAvatar):
    async def generate(self, image_bytes, audio_file_id, **kwargs):
        raise ImageValidationError("Image too small")


class EngineDownAvatar(HappyAvatar):
    async def generate(self, image_bytes, audio_file_id, **kwargs):
        raise AvatarEngineError("Model server unreachable", status_code=503)


@pytest.fixture
def app():
    return create_app()


def _post(client, **form):
    return client.post(
        "/api/v1/avatar/generate",
        files={"image": ("face.png", _png(), "image/png")},
        data={"audio_file_id": "a" * 32 + ".wav", **form},
    )


def test_generate_success(app):
    app.dependency_overrides[get_avatar_service] = lambda: HappyAvatar()
    resp = _post(TestClient(app))
    assert resp.status_code == 200
    assert resp.json()["codec"] == "h264"


def test_validation_maps_to_422(app):
    app.dependency_overrides[get_avatar_service] = lambda: ValidationFailAvatar()
    assert _post(TestClient(app)).status_code == 422


def test_engine_down_maps_to_503(app):
    app.dependency_overrides[get_avatar_service] = lambda: EngineDownAvatar()
    assert _post(TestClient(app)).status_code == 503


def test_bad_preprocess_rejected(app):
    app.dependency_overrides[get_avatar_service] = lambda: HappyAvatar()
    assert _post(TestClient(app), preprocess="hd").status_code == 422


def test_avatar_health(app):
    app.dependency_overrides[get_avatar_service] = lambda: HappyAvatar()
    resp = TestClient(app).get("/api/v1/avatar/health")
    assert resp.status_code == 200
    assert resp.json()["checkpoints_present"] is True
