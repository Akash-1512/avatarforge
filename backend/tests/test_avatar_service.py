"""AvatarService — mocked engine client, real validation/ffmpeg/storage."""

import io
import subprocess

import pytest
from PIL import Image

from backend.services.avatar.client import AvatarEngineError
from backend.services.avatar.service import AvatarService
from backend.services.storage.local import LocalStorageBackend


def _face_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(200, 170, 150)).save(buf, format="PNG")
    return buf.getvalue()


def _raw_video() -> bytes:
    return subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=256x256:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            "-f",
            "mp4",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout


class FakeClient:
    def __init__(self, *, fail: AvatarEngineError | None = None):
        self._fail = fail
        self.calls = 0

    async def infer(self, image_bytes, image_ext, audio_bytes, **kwargs):
        self.calls += 1
        if self._fail:
            raise self._fail
        return _raw_video()

    async def health(self):
        return {"status": "ok"}


@pytest.fixture
def storage(tmp_path):
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture
async def audio_id(storage):
    stored = await storage.save_bytes(b"RIFF" + b"\x00" * 100, "wav")
    return stored.file_id


@pytest.mark.asyncio
async def test_generate_happy_path(storage, audio_id):
    svc = AvatarService({"sadtalker": FakeClient()}, storage)
    resp = await svc.generate(_face_png(), audio_id)
    assert resp.codec == "h264"
    assert resp.video_url.startswith("/api/v1/media/")
    assert storage.resolve_path(resp.file_id) is not None
    assert resp.video_duration_sec >= 0.9


@pytest.mark.asyncio
async def test_missing_audio_raises_not_found(storage):
    svc = AvatarService({"sadtalker": FakeClient()}, storage)
    with pytest.raises(FileNotFoundError, match="not found"):
        await svc.generate(_face_png(), "0" * 32 + ".wav")


@pytest.mark.asyncio
async def test_engine_error_recorded_and_reraised(storage, audio_id):
    recorded = []

    async def recorder(payload):
        recorded.append(payload)

    err = AvatarEngineError("model server down", status_code=503)
    svc = AvatarService({"sadtalker": FakeClient(fail=err)}, storage, usage_recorder=recorder)
    with pytest.raises(AvatarEngineError):
        await svc.generate(_face_png(), audio_id)
    assert len(recorded) == 1
    assert recorded[0]["success"] is False


@pytest.mark.asyncio
async def test_success_recorded(storage, audio_id):
    recorded = []

    async def recorder(payload):
        recorded.append(payload)

    svc = AvatarService({"sadtalker": FakeClient()}, storage, usage_recorder=recorder)
    await svc.generate(_face_png(), audio_id)
    assert recorded[0]["success"] is True
    assert recorded[0]["video_duration_sec"] >= 0.9


@pytest.mark.asyncio
async def test_engine_routing_explicit(storage, audio_id):
    """Explicit engine choice routes to that engine's client."""
    sad, hun = FakeClient(), FakeClient()
    svc = AvatarService({"sadtalker": sad, "hunyuan": hun}, storage)

    resp = await svc.generate(_face_png(), audio_id, engine="hunyuan")
    assert resp.engine == "hunyuan"
    assert hun.calls == 1 and sad.calls == 0


@pytest.mark.asyncio
async def test_engine_routing_default(storage, audio_id):
    """No engine specified -> default engine handles it."""
    sad, hun = FakeClient(), FakeClient()
    svc = AvatarService({"sadtalker": sad, "hunyuan": hun}, storage, default_engine="sadtalker")

    resp = await svc.generate(_face_png(), audio_id)
    assert resp.engine == "sadtalker"
    assert sad.calls == 1 and hun.calls == 0


def test_unconfigured_engine_raises_503(storage):
    """Requesting an engine that isn't configured fails fast with 503."""
    svc = AvatarService({"sadtalker": FakeClient()}, storage)
    with pytest.raises(AvatarEngineError) as exc_info:
        svc.resolve_engine("hunyuan")
    assert exc_info.value.status_code == 503
    assert "not configured" in str(exc_info.value)


def test_fal_engine_registered_when_key_present(monkeypatch):
    """get_avatar_service wires the fal engine iff FAL_API_KEY is set."""
    from backend.config import get_settings
    from backend.services.avatar.service import get_avatar_service

    monkeypatch.setenv("FAL_API_KEY", "k-123")
    get_settings.cache_clear()
    get_avatar_service.cache_clear()
    svc = get_avatar_service()
    assert "fal" in svc.engines
    assert "sadtalker" in svc.engines

    get_settings.cache_clear()
    get_avatar_service.cache_clear()
