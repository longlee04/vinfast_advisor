"""Private MinIO storage adapter for uploaded images."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Final

import anyio
from minio.error import InvalidResponseError, MinioException, S3Error, ServerError

from src.document.infrastructure.minio_storage import MinioClient
from src.document.infrastructure.settings import DocumentSettings
from src.images.application.errors import (
    ImageStorageUnavailableError,
    ImageUploadRejectedError,
)
from src.images.application.ports import ImageStorage, StoredImage
from src.images.domain.entities import Image
from src.images.domain.values import ImageId

READ_CHUNK_SIZE: Final[int] = 64 * 1024
ALLOWED_IMAGE_EXTENSIONS: Final[dict[str, frozenset[str]]] = {
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/webp": frozenset({".webp"}),
}
ALLOWED_IMAGE_MIME_TYPES: Final[frozenset[str]] = frozenset(ALLOWED_IMAGE_EXTENSIONS)
IMAGE_OBJECT_PREFIX: Final[str] = "images/"


class MinioImageStorage(ImageStorage):
    """Stores image bytes privately under a dedicated object prefix."""

    def __init__(self, client: MinioClient, settings: DocumentSettings) -> None:
        self._client = client
        self._settings = settings

    async def upload(
        self,
        image_id: ImageId,
        data: BinaryIO,
        filename: str,
        content_type: str,
    ) -> StoredImage:
        """Bound and hash content before one private synchronous SDK upload."""
        self._validate_content_type(filename, content_type)
        payload, content_hash = await anyio.to_thread.run_sync(self._read_bounded, data)
        object_key = self._generate_object_key(image_id)
        try:
            await anyio.to_thread.run_sync(
                self._put,
                object_key,
                payload,
                content_type,
            )
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise ImageStorageUnavailableError() from error
        return StoredImage(object_key, content_hash, content_type, len(payload))

    async def remove(self, object_key: str) -> None:
        """Remove a stored image object as best-effort cleanup."""
        try:
            await anyio.to_thread.run_sync(self._remove, object_key)
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise ImageStorageUnavailableError() from error

    async def presign(self, image: Image) -> str:
        """Create a private GET URL with the fixed 60-second expiry."""
        try:
            return await anyio.to_thread.run_sync(self._presign, image.object_key)
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise ImageStorageUnavailableError() from error

    def _validate_content_type(self, filename: str, content_type: str) -> None:
        if content_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise ImageUploadRejectedError(status_code=415)
        if not filename.lower().endswith(tuple(ALLOWED_IMAGE_EXTENSIONS[content_type])):
            raise ImageUploadRejectedError(status_code=415)

    def _read_bounded(self, data: BinaryIO) -> tuple[bytes, str]:
        payload = bytearray()
        digest = sha256()
        while chunk := data.read(READ_CHUNK_SIZE):
            payload.extend(chunk)
            digest.update(chunk)
            if len(payload) > self._settings.max_file_size_bytes:
                raise ImageUploadRejectedError(status_code=413)
        return bytes(payload), digest.hexdigest()

    def _generate_object_key(self, image_id: ImageId) -> str:
        return f"{IMAGE_OBJECT_PREFIX}{image_id.value}/{token_urlsafe(24)}"

    def _put(self, object_key: str, payload: bytes, content_type: str) -> None:
        with SpooledTemporaryFile(max_size=self._settings.max_file_size_bytes, mode="w+b") as stream:
            stream.write(payload)
            stream.seek(0)
            self._client.put_object(
                bucket_name=self._settings.bucket_name,
                object_name=object_key,
                data=stream,
                length=len(payload),
                content_type=content_type,
            )

    def _remove(self, object_key: str) -> None:
        self._client.remove_object(
            bucket_name=self._settings.bucket_name,
            object_name=object_key,
        )

    def _presign(self, object_key: str) -> str:
        return self._client.presigned_get_object(
            bucket_name=self._settings.bucket_name,
            object_name=object_key,
            expires=timedelta(seconds=self._settings.presigned_download_ttl_seconds),
        )
