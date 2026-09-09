"""Todo 4 storage and compensation behavior tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Final

import pytest

from src.document.application.contracts import CreateUploadedDocument, UploadDocumentCommand
from src.document.application.errors import (
    DocumentPersistenceError,
    DocumentStorageUnavailableError,
    DocumentUploadRejectedError,
)
from src.document.application.ports import ObjectStorage
from src.document.domain.entities import Document
from src.document.domain.values import ApprovalStatus, DocumentId, ProcessingStatus
from src.document.infrastructure.minio_storage import READ_CHUNK_SIZE, MinioObjectStorage
from src.document.infrastructure.object_keys import generate_object_key
from src.document.infrastructure.settings import DocumentSettings

MAX_FILE_SIZE: Final[int] = 25 * 1024 * 1024


@dataclass
class RecordingMinioClient:
    """Deterministic synchronous MinIO SDK seam."""

    put_calls: list[tuple[str, str, int, str]]
    removed_keys: list[str]
    fail_put: bool = False
    fail_remove: bool = False
    fail_presign: bool = False
    presign_expiries: list[timedelta] | None = None
    read_payload: bytes = b"stored policy"
    read_response: RecordingMinioResponse | None = None

    def get_object(self, *, bucket_name: str, object_name: str) -> RecordingMinioResponse:
        assert bucket_name == "documents"
        assert object_name
        response = RecordingMinioResponse(self.read_payload)
        self.read_response = response
        return response

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
    ) -> None:
        if self.fail_put:
            from minio.error import S3Error

            raise S3Error("AccessDenied", "provider detail", "resource", "request", "host", None)
        self.put_calls.append((bucket_name, object_name, length, content_type))
        assert len(data.read()) == length

    def remove_object(self, *, bucket_name: str, object_name: str) -> None:
        self.removed_keys.append(f"{bucket_name}/{object_name}")
        if self.fail_remove:
            from minio.error import S3Error

            raise S3Error("AccessDenied", "provider detail", "resource", "request", "host", None)

    def presigned_get_object(self, *, bucket_name: str, object_name: str, expires: timedelta) -> str:
        if self.presign_expiries is not None:
            self.presign_expiries.append(expires)
        if self.fail_presign:
            from minio.error import S3Error

            raise S3Error("AccessDenied", "provider detail", "resource", "request", "host", None)
        return f"https://storage.test/{bucket_name}/{object_name}?expires={expires}"


@dataclass
class RecordingMinioResponse:
    """Record mandatory response cleanup after a private object read."""

    payload: bytes
    closed: bool = False
    released: bool = False

    def read(self) -> bytes:
        return self.payload

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


@dataclass
class RecordingStream:
    """Binary stream recording every bounded read request and returned chunk."""

    payload: bytes
    requested_sizes: list[int]
    returned_chunks: list[bytes]
    offset: int = 0

    def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        self.returned_chunks.append(chunk)
        return chunk


@dataclass
class RecordingRepository:
    added: list[Document]
    fail_add: bool = False

    async def add(self, document: Document) -> Document:
        if self.fail_add:
            raise DocumentPersistenceError()
        self.added.append(document)
        return document


@dataclass(frozen=True)
class RecordingTransaction:
    documents: RecordingRepository


@dataclass
class CommitFailingUnitOfWork:
    """Test UoW that persists then raises as its transaction commits."""

    repository: RecordingRepository
    transaction_count: int = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[RecordingTransaction]:
        self.transaction_count += 1
        yield RecordingTransaction(self.repository)
        raise RuntimeError("database commit failed")


@dataclass
class SuccessfulUnitOfWork:
    """Test UoW that commits on normal transaction exit."""

    repository: RecordingRepository
    transaction_count: int = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[RecordingTransaction]:
        self.transaction_count += 1
        yield RecordingTransaction(self.repository)


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


def test_generates_object_key_from_document_id_without_filename() -> None:
    # Given
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When
    key = generate_object_key(document_id, "../../secrets.pdf")

    # Then
    assert key.startswith(f"document/{document_id.value}/")
    assert "secrets" not in key
    assert ".." not in key


def test_generates_image_object_key_for_image_mime_and_type() -> None:
    # Given
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When
    key_by_mime = generate_object_key(document_id, "car.png", content_type="image/png")
    key_by_type = generate_object_key(document_id, "bike.jpg", document_type="VEHICLE_IMAGE")

    # Then
    assert key_by_mime.startswith(f"image/{document_id.value}/")
    assert key_by_type.startswith(f"image/{document_id.value}/")


@pytest.mark.asyncio
async def test_uploads_bounded_content_and_calculates_metadata(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [])
    storage = MinioObjectStorage(client, settings)
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When
    stream = RecordingStream(b"policy", [], [])
    stored = await storage.upload(document_id, stream, "../../policy.pdf", "application/pdf")

    # Then
    assert stored.byte_size == len(b"policy")
    assert stored.content_hash == "823412d1eacb67956220e532959f0104603057c88704863ca38e7cd188fda812"
    assert client.put_calls == [("documents", stored.object_key, len(b"policy"), "application/pdf")]
    assert stream.requested_sizes != []
    assert all(size == READ_CHUNK_SIZE for size in stream.requested_sizes)
    assert all(len(chunk) <= READ_CHUNK_SIZE for chunk in stream.returned_chunks)


@pytest.mark.asyncio
async def test_rejects_upload_larger_than_limit_before_minio_put(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [])
    storage = MinioObjectStorage(client, settings)
    document_id = DocumentId("123e4567-e89b-12d3-a456-426614174000")

    # When / Then
    stream = RecordingStream(b"x" * (MAX_FILE_SIZE + 1), [], [])

    # When / Then
    with pytest.raises(DocumentUploadRejectedError) as raised:
        await storage.upload(document_id, stream, "policy.pdf", "application/pdf")
    assert raised.value.status_code == 413
    assert client.put_calls == []
    assert all(size == READ_CHUNK_SIZE for size in stream.requested_sizes)
    assert all(len(chunk) <= READ_CHUNK_SIZE for chunk in stream.returned_chunks)


@pytest.mark.asyncio
async def test_presigns_with_exact_60_second_expiry(settings: DocumentSettings) -> None:
    # Given
    expiries: list[timedelta] = []
    client = RecordingMinioClient([], [], presign_expiries=expiries)
    storage = MinioObjectStorage(client, settings)
    document = Document(
        id=DocumentId("123e4567-e89b-12d3-a456-426614174000"),
        title="Policy",
        content_hash="a" * 64,
        created_by="admin-1",
        created_at=datetime.now(UTC),
        approval_status=ApprovalStatus.DRAFT,
        processing_status=ProcessingStatus.NOT_STARTED,
        object_key="documents/123/object",
    )

    # When
    url = await storage.presign(document)

    # Then
    assert url.startswith("https://storage.test/documents/")
    assert expiries == [timedelta(seconds=60)]


@pytest.mark.asyncio
async def test_reads_private_object_bytes_and_releases_the_connection(settings: DocumentSettings) -> None:
    client = RecordingMinioClient([], [], read_payload=b"private policy bytes")
    storage = MinioObjectStorage(client, settings)

    payload = await storage.read("document/private/policy.txt")

    assert payload == b"private policy bytes"
    assert client.read_response is not None
    assert client.read_response.closed is True
    assert client.read_response.released is True


@pytest.mark.asyncio
async def test_maps_presign_failure_to_retryable_application_error(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [], fail_presign=True)
    storage = MinioObjectStorage(client, settings)
    document = Document(
        id=DocumentId("123e4567-e89b-12d3-a456-426614174000"),
        title="Policy",
        content_hash="a" * 64,
        created_by="admin-1",
        created_at=datetime.now(UTC),
        approval_status=ApprovalStatus.DRAFT,
        processing_status=ProcessingStatus.NOT_STARTED,
        object_key="documents/123/object",
    )

    # When / Then
    with pytest.raises(DocumentStorageUnavailableError) as raised:
        await storage.presign(document)
    assert raised.value.status_code == 503


@pytest.mark.asyncio
async def test_removes_uploaded_object_when_metadata_persistence_fails(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [])
    storage: ObjectStorage = MinioObjectStorage(client, settings)
    repository = RecordingRepository([], fail_add=True)
    use_case = CreateUploadedDocument(SuccessfulUnitOfWork(repository), storage)
    command = UploadDocumentCommand(
        title="Policy",
        actor_id="admin-1",
        data=BytesIO(b"policy"),
        filename="policy.pdf",
        content_type="application/pdf",
    )

    # When / Then
    with pytest.raises(DocumentPersistenceError):
        await use_case.execute(command)
    assert len(client.put_calls) == 1
    assert client.removed_keys == [f"documents/{client.put_calls[0][1]}"]


@pytest.mark.asyncio
async def test_removes_uploaded_object_when_transaction_commit_fails(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [])
    storage: ObjectStorage = MinioObjectStorage(client, settings)
    repository = RecordingRepository([])
    uow = CommitFailingUnitOfWork(repository)
    use_case = CreateUploadedDocument(uow, storage)
    command = UploadDocumentCommand("Policy", "admin-1", BytesIO(b"policy"), "policy.pdf", "application/pdf")

    # When / Then
    with pytest.raises(DocumentPersistenceError) as raised:
        await use_case.execute(command)
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "database commit failed"
    assert uow.transaction_count == 1
    assert repository.added != []
    assert client.removed_keys == [f"documents/{client.put_calls[0][1]}"]


@pytest.mark.asyncio
async def test_preserves_commit_cause_when_compensation_cleanup_fails(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [], fail_remove=True)
    storage: ObjectStorage = MinioObjectStorage(client, settings)
    uow = CommitFailingUnitOfWork(RecordingRepository([]))
    use_case = CreateUploadedDocument(uow, storage)
    command = UploadDocumentCommand("Policy", "admin-1", BytesIO(b"policy"), "policy.pdf", "application/pdf")

    # When / Then
    with pytest.raises(DocumentPersistenceError) as raised:
        await use_case.execute(command)
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "database commit failed"
    assert len(client.removed_keys) == 1


@pytest.mark.asyncio
async def test_does_not_compensate_when_transaction_commits(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [])
    storage: ObjectStorage = MinioObjectStorage(client, settings)
    repository = RecordingRepository([])
    uow = SuccessfulUnitOfWork(repository)
    use_case = CreateUploadedDocument(uow, storage)
    command = UploadDocumentCommand("Policy", "admin-1", BytesIO(b"policy"), "policy.pdf", "application/pdf")

    # When
    created = await use_case.execute(command)

    # Then
    assert created == repository.added[0]
    assert uow.transaction_count == 1
    assert client.removed_keys == []


@pytest.mark.asyncio
async def test_maps_minio_upload_failure_without_creating_metadata(settings: DocumentSettings) -> None:
    # Given
    client = RecordingMinioClient([], [], fail_put=True)
    storage: ObjectStorage = MinioObjectStorage(client, settings)
    repository = RecordingRepository([])
    use_case = CreateUploadedDocument(repository, storage)
    command = UploadDocumentCommand("Policy", "admin-1", BytesIO(b"policy"), "policy.pdf", "application/pdf")

    # When / Then
    with pytest.raises(DocumentStorageUnavailableError) as raised:
        await use_case.execute(command)
    assert raised.value.status_code == 503
    assert repository.added == []
