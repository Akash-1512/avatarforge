"""Local storage backend — save, resolve, and traversal protection."""

import pytest

from backend.services.storage.local import LocalStorageBackend


@pytest.fixture
def storage(tmp_path):
    return LocalStorageBackend(str(tmp_path))


@pytest.mark.asyncio
async def test_save_and_resolve(storage):
    stored = await storage.save_bytes(b"fake-wav-data", "wav")
    assert stored.url.startswith("/api/v1/media/")
    assert stored.size_bytes == 13
    path = storage.resolve_path(stored.file_id)
    assert path is not None
    with open(path, "rb") as f:
        assert f.read() == b"fake-wav-data"


def test_path_traversal_blocked(storage):
    assert storage.resolve_path("../../etc/passwd") is None
    assert storage.resolve_path("..%2F..%2Fetc%2Fpasswd") is None
    assert storage.resolve_path("notahexid.wav") is None
    assert storage.resolve_path("a" * 32 + ".exe") is None


def test_missing_file_returns_none(storage):
    assert storage.resolve_path("0" * 32 + ".wav") is None
