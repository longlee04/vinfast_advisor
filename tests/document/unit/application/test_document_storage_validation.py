"""Document upload MIME and filename extension validation tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO

import pytest

from src.document.application.errors import DocumentUploadRejectedError
from src.document.domain.values import DocumentId
from src.document.infrastructure.minio_storage import MinioObjectStorage
from src.document.infrastructure.settings import DocumentSettings


@dataclass
class RecordingMinioClient:
    """Deterministic synchronous MinIO SDK seam."""

    put_calls: list[tuple[str, str, int, str]]

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
    ) -> None:
        self.put_calls.append((bucket_name, object_name, length, content_type))
        assert len(data.read()) == length

    def presigned_get_object(self, *, bucket_name: str, object_name: str, expires: timedelta) -> str:
        return f"https://storage.test/{bucket_name}/{object_name}?expires={expires}"


@pytest.fixture
def settings() -> DocumentSettings:
    return DocumentSettings(
        enabled=True,
        database_url="postgresql+asyncpg://user:password@localhost:5432/documents",
        minio_endpoint="http://localhost:9000",
        bucket_name="documents",
        access_key="access",
        secret_key="secret",
    )


@pytest.mark.asyncio
async def test_rejects_unsupported_mime_type_before_minio_put(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([])
    storage = MinioObjectStorage(client, settings)
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When / Then
    with pytest.raises(DocumentUploadRejectedError) as raised:
        await storage.upload(document_id, BytesIO(b"policy"), "policy.exe", "application/octet-stream")
    assert raised.value.status_code == 415
    assert client.put_calls == []


@pytest.mark.asyncio
async def test_accepts_text_csv_with_csv_extension(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([])
    storage = MinioObjectStorage(client, settings)
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When
    stored = await storage.upload(document_id, BytesIO(b"name,value\npolicy,active\n"), "policy.csv", "text/csv")

    # Then
    assert stored.byte_size == len(b"name,value\npolicy,active\n")
    assert client.put_calls == [("documents", stored.object_key, stored.byte_size, "text/csv")]


@pytest.mark.asyncio
async def test_accepts_reviewed_html_snapshot_with_html_extension(settings: DocumentSettings) -> None:
    client = RecordingMinioClient([])
    storage = MinioObjectStorage(client, settings)
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    stored = await storage.upload(
        document_id,
        BytesIO(b"<!doctype html><html><body>Policy</body></html>"),
        "policy.html",
        "text/html",
    )

    assert stored.content_type == "text/html"
    assert client.put_calls[0][3] == "text/html"


@pytest.mark.asyncio
async def test_rejects_csv_mime_with_non_csv_extension_before_minio_put(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([])
    storage = MinioObjectStorage(client, settings)
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When / Then
    with pytest.raises(DocumentUploadRejectedError) as raised:
        await storage.upload(document_id, BytesIO(b"name,value\n"), "policy.txt", "text/csv")
    assert raised.value.status_code == 415
    assert client.put_calls == []


@pytest.mark.asyncio
async def test_rejects_filename_extension_mismatched_to_mime_before_minio_put(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([])
    storage = MinioObjectStorage(client, settings)
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When / Then
    with pytest.raises(DocumentUploadRejectedError) as raised:
        await storage.upload(document_id, BytesIO(b"policy"), "policy.txt", "application/pdf")
    assert raised.value.status_code == 415
    assert client.put_calls == []
