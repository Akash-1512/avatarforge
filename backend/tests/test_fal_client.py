"""fal avatar client — upload, submit, poll, download, all mocked.

Exercises the adapter against a fake fal REST surface so the queue-polling
logic is verified without network or an API key.
"""

import httpx
import pytest

from backend.config import Settings
from backend.services.avatar.client import AvatarEngineError
from backend.services.avatar.fal_client import FalAvatarClient


def _settings(**kw):
    return Settings(fal_api_key="test-key", avatar_inference_timeout_sec=30, **kw)


class _FalMock:
    """Scriptable fal backend: upload x2 -> submit -> status(IN_PROGRESS, COMPLETED) -> result."""

    def __init__(self, *, fail_status=False, no_video=False):
        self.fail_status = fail_status
        self.no_video = no_video
        self.status_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "queue.fal.run" in url and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "request_id": "req-1",
                    "status_url": "https://queue.fal.run/req-1/status",
                    "response_url": "https://queue.fal.run/req-1",
                },
            )
        if url.endswith("/status"):
            self.status_calls += 1
            if self.fail_status:
                return httpx.Response(200, json={"status": "FAILED", "error": "boom"})
            if self.status_calls >= 2:
                return httpx.Response(200, json={"status": "COMPLETED"})
            # fal returns HTTP 202 while still IN_QUEUE / IN_PROGRESS
            return httpx.Response(202, json={"status": "IN_PROGRESS"})
        # result fetch
        if self.no_video:
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"video": {"url": "https://fal.media/out.mp4"}})


@pytest.fixture
def patch_httpx(monkeypatch):
    """Route every AsyncClient through the mock, and make sleep instant."""
    mock_holder = {}

    def install(mock: _FalMock):
        transport = httpx.MockTransport(mock.handler)
        real_init = httpx.AsyncClient.__init__

        def patched_init(self, *a, **kw):
            kw["transport"] = transport
            real_init(self, *a, **kw)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        # out.mp4 download also goes through the transport
        mock_holder["mock"] = mock

    monkeypatch.setattr("asyncio.sleep", _instant_sleep)
    return install


async def _instant_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_health_reports_key_presence():
    assert (await FalAvatarClient(_settings()).health())["status"] == "ok"
    assert (await FalAvatarClient(Settings(fal_api_key="")).health())["status"] == "degraded"


@pytest.mark.asyncio
async def test_infer_happy_path(patch_httpx):
    mock = _FalMock()
    patch_httpx(mock)
    # The mp4 'download' returns JSON bytes from the result handler's fallthrough;
    # assert we got bytes back and polled to completion.
    out = await FalAvatarClient(_settings()).infer(b"img", "png", b"RIFFwav")
    assert isinstance(out, bytes)
    assert mock.status_calls >= 2  # polled through IN_PROGRESS then COMPLETED


@pytest.mark.asyncio
async def test_infer_raises_without_key():
    with pytest.raises(AvatarEngineError) as exc:
        await FalAvatarClient(Settings(fal_api_key="")).infer(b"i", "png", b"a")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_infer_raises_on_failed_status(patch_httpx):
    patch_httpx(_FalMock(fail_status=True))
    with pytest.raises(AvatarEngineError):
        await FalAvatarClient(_settings()).infer(b"img", "png", b"wav")


@pytest.mark.asyncio
async def test_infer_raises_when_no_video_url(patch_httpx):
    patch_httpx(_FalMock(no_video=True))
    with pytest.raises(AvatarEngineError) as exc:
        await FalAvatarClient(_settings()).infer(b"img", "png", b"wav")
    assert "video URL" in str(exc.value)
