from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings


class StorageBackend(ABC):
    @abstractmethod
    async def put(self, key: str, body: BinaryIO | bytes, content_type: str | None = None) -> str:
        """Store file; return path or URI."""
        ...

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve file bytes."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete file."""
        ...


def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "gcs":
        from app.storage.gcs import GCSStorage
        return GCSStorage()
    from app.storage.local import LocalStorage
    return LocalStorage()
