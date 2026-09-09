"""Private MinIO ObjectStorage adapter with bounded streaming uploads."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Final, Protocol

import anyio
from minio.error import InvalidResponseError, MinioException, S3Error, ServerError

from src.document.application.errors import DocumentStorageUnavailableError, DocumentUploadRejectedError
from src.document.application.ports import StoredObject
from src.document.domain.entities import Document
from src.document.domain.values import DocumentId
from src.document.infrastructure.object_keys import generate_object_key
from src.document.infrastructure.settings import DocumentSettings

READ_CHUNK_SIZE: Final[int] = 64 * 1024
ALLOWED_EXTENSIONS: Final[dict[str, frozenset[str]]] = {
    "application/pdf": frozenset({".pdf"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset({".docx"}),
    "text/plain": frozenset({".txt"}),
    "text/html": frozenset({".html", ".htm"}),
    "text/csv": frozenset({".csv"}),
}


class MinioResponse(Protocol):
    """Lifecycle of a synchronous MinIO object response."""

    def read(self) -> bytes: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class MinioClient(Protocol):
    """Narrow synchronous MinIO SDK seam for deterministic adapter tests."""

    def get_object(self, *, bucket_name: str, object_name: str) -> MinioResponse: ...

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str,
    ) -> None: ...

    def remove_object(self, *, bucket_name: str, object_name: str) -> None: ...

    def presigned_get_object(self, *, bucket_name: str, object_name: str, expires: timedelta) -> str: ...


class MinioObjectStorage:
    """Stores Document bytes privately without exposing SDK failures."""

    def __init__(self, client: MinioClient, settings: DocumentSettings) -> None:
        self._client = client
        self._settings = settings

    async def upload(
        self,
        document_id: DocumentId,
        data: BinaryIO,
        filename: str,
        content_type: str,
    ) -> StoredObject:
        """Bound and hash content before one private synchronous SDK upload."""
        self._validate_content_type(filename, content_type)
        payload, content_hash = await anyio.to_thread.run_sync(self._read_bounded, data)
        object_key = generate_object_key(document_id, filename, content_type=content_type)
        try:
            await anyio.to_thread.run_sync(
                self._put,
                object_key,
                payload,
                content_type,
            )
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise DocumentStorageUnavailableError() from error
        return StoredObject(object_key, content_hash, content_type, len(payload))

    async def remove(self, object_key: str) -> None:
        """Remove an uploaded object as best-effort database-failure compensation."""
        try:
            await anyio.to_thread.run_sync(self._remove, object_key)
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise DocumentStorageUnavailableError() from error

    async def read(self, object_key: str) -> bytes:
        """Read private object bytes directly without exposing a presigned URL."""
        try:
            return await anyio.to_thread.run_sync(self._read_object, object_key)
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise DocumentStorageUnavailableError() from error

    async def presign(self, document: Document) -> str:
        """Create a private GET URL with the fixed 60-second expiry."""
        if document.object_key is None:
            raise DocumentStorageUnavailableError()
        try:
            return await anyio.to_thread.run_sync(self._presign, document.object_key)
        except (InvalidResponseError, MinioException, S3Error, ServerError) as error:
            raise DocumentStorageUnavailableError() from error

    def _validate_content_type(self, filename: str, content_type: str) -> None:
        if content_type not in self._settings.allowed_mime_types:
            raise DocumentUploadRejectedError(status_code=415)
        if not filename.lower().endswith(tuple(ALLOWED_EXTENSIONS[content_type])):
            raise DocumentUploadRejectedError(status_code=415)

    def _read_bounded(self, data: BinaryIO) -> tuple[bytes, str]:
        payload = bytearray()
        digest = sha256()
        while chunk := data.read(READ_CHUNK_SIZE):
            payload.extend(chunk)
            digest.update(chunk)
            if len(payload) > self._settings.max_file_size_bytes:
                raise DocumentUploadRejectedError(status_code=413)
        return bytes(payload), digest.hexdigest()

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
        self._client.remove_object(bucket_name=self._settings.bucket_name, object_name=object_key)

    def _read_object(self, object_key: str) -> bytes:
        response = self._client.get_object(
            bucket_name=self._settings.bucket_name,
            object_name=object_key,
        )
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def _presign(self, object_key: str) -> str:
        return self._client.presigned_get_object(
            bucket_name=self._settings.bucket_name,
            object_name=object_key,
            expires=timedelta(seconds=60),
        )
