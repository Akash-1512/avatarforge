"""Storage contract — local filesystem now, Azure Blob in a later phase."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StoredFile:
    file_id: str
    path: str
    url: str
    size_bytes: int


class BaseStorageBackend(ABC):
    @abstractmethod
    async def save_bytes(self, data: bytes, extension: str) -> StoredFile:
        """Persist bytes, return an addressable file record."""

    @abstractmethod
    def resolve_path(self, file_id: str) -> str | None:
        """Return the absolute path for a stored file id, or None if missing/invalid."""
