"""HTTP downloader and MinIO storage adapters for normalized vehicle images."""

from __future__ import annotations

from io import BytesIO
from typing import Final

import anyio
import httpx
from minio.error import InvalidResponseError, MinioException, S3Error, ServerError

from src.document.infrastructure.minio_storage import MinioClient
from src.document.infrastructure.settings import DocumentSettings
from src.products.application.vehicle_image_sync import (
    DOWNLOAD_TIMEOUT_SECONDS,
    ImageDownloader,
    ImageStorage,
)

_IMAGE_CONTENT_TYPE: Final = "image/png"


class VehicleImageDownloadError(ValueError):
    """Raised when a vehicle image cannot be fetched from its public URL."""


class VehicleImageStorageError(ValueError):
    """Raised when MinIO cannot store a normalized vehicle image."""


class HttpVehicleImageDownloader(ImageDownloader):
    """Download public vehicle images using the installed async HTTP client."""

    async def fetch(self, url: str) -> bytes:
        """Return successful response bytes within the fixed download timeout."""
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise VehicleImageDownloadError("vehicle image download failed") from error
        return response.content


class MinioVehicleImageStorage(ImageStorage):
    """Store normalized vehicle PNG assets in the configured private MinIO bucket."""

    def __init__(self, client: MinioClient, settings: DocumentSettings) -> None:
        self._client = client
        self._settings = settings

    async def put(self, object_key: str, payload: bytes) -> None:
        """Store payload under object_key without blocking the async event loop."""
        try:
            await anyio.to_thread.run_sync(self._put, object_key, payload)
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise VehicleImageStorageError("vehicle image storage failed") from error

    def _put(self, object_key: str, payload: bytes) -> None:
        self._client.put_object(
            bucket_name=self._settings.bucket_name,
            object_name=object_key,
            data=BytesIO(payload),
            length=len(payload),
            content_type=_IMAGE_CONTENT_TYPE,
        )
