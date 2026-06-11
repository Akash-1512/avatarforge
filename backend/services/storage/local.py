"""Local filesystem storage backend.

Files are stored flat under settings.local_storage_path with UUID names.
resolve_path validates the file id against a strict pattern — this is the
path-traversal guard for the media-serving endpoint.
"""

import re
import uuid
from functools import lru_cache
from pathlib import Path

import anyio

from backend.config import get_settings
from backend.services.storage.base import BaseStorageBackend, StoredFile

_SAFE_FILE_ID = re.compile(r"^[a-f0-9]{32}\.(wav|mp4|png|jpg)$")


class LocalStorageBackend(BaseStorageBackend):
    def __init__(self, base_path: str, url_prefix: str = "/api/v1/media"):
        self.base_path = Path(base_path)
        self.url_prefix = url_prefix
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_bytes(self, data: bytes, extension: str) -> StoredFile:
        file_id = f"{uuid.uuid4().hex}.{extension.lstrip('.')}"
        target = self.base_path / file_id
        await anyio.to_thread.run_sync(target.write_bytes, data)
        return StoredFile(
            file_id=file_id,
            path=str(target),
            url=f"{self.url_prefix}/{file_id}",
            size_bytes=len(data),
        )

    def resolve_path(self, file_id: str) -> str | None:
        if not _SAFE_FILE_ID.match(file_id):
            return None
        target = (self.base_path / file_id).resolve()
        if not str(target).startswith(str(self.base_path.resolve())):
            return None
        return str(target) if target.exists() else None


@lru_cache
def get_storage() -> LocalStorageBackend:
    return LocalStorageBackend(get_settings().local_storage_path)
