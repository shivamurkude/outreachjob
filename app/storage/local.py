from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self) -> None:
        settings = get_settings()
        self.root = Path(settings.storage_local_path)
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, body: BinaryIO | bytes, content_type: str | None = None) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_bytes(body.read())
        return str(path)

    async def get(self, key: str) -> bytes:
        path = self.root / key
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self.root / key
        if path.exists():
            path.unlink()
