from typing import BinaryIO

from google.cloud import storage

from app.core.config import get_settings
from app.storage.base import StorageBackend


class GCSStorage(StorageBackend):
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket_name = settings.gcs_bucket_name or "findmyjob-uploads"
        self._client = storage.Client()
        self._bucket = self._client.bucket(self.bucket_name)

    async def put(self, key: str, body: BinaryIO | bytes, content_type: str | None = None) -> str:
        blob = self._bucket.blob(key)
        if isinstance(body, bytes):
            blob.upload_from_string(body, content_type=content_type or "application/octet-stream")
        else:
            blob.upload_from_file(body, content_type=content_type or "application/octet-stream")
        return f"gs://{self.bucket_name}/{key}"

    async def get(self, key: str) -> bytes:
        blob = self._bucket.blob(key)
        if not blob.exists():
            raise FileNotFoundError(key)
        return blob.download_as_bytes()

    async def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        if blob.exists():
            blob.delete()
