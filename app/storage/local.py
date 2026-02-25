from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.logging import get_logger
from app.storage.base import StorageBackend

log = get_logger(__name__)


class LocalStorage(StorageBackend):
    def __init__(self) -> None:
        log.debug("LocalStorage.__init__")
        settings = get_settings()
        self.root = Path(settings.storage_local_path)
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, body: BinaryIO | bytes, content_type: str | None = None) -> str:
        log.debug("LocalStorage.put", key=key, size=len(body) if isinstance(body, bytes) else None)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_bytes(body.read())
        log.debug("LocalStorage.put_ok", key=key)
        return str(path)

    async def get(self, key: str) -> bytes:
        log.debug("LocalStorage.get", key=key)
        path = self.root / key
        if not path.exists():
            log.warning("LocalStorage.get_not_found", key=key)
            raise FileNotFoundError(key)
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        log.debug("LocalStorage.delete", key=key)
        path = self.root / key
        if path.exists():
            path.unlink()
        log.debug("LocalStorage.delete_ok", key=key)
