"""HTTP contracts for the enabled Document presentation router."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import BinaryIO, Self

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.domain.authorization import Role
from src.document.application.contracts import (
    ArchiveDocument,
    CreateUploadedDocument,
    DetailDocument,
    DownloadDocument,
    ListDocuments,
)
from src.document.application.ports import StoredObject
from src.document.domain.entities import Document
from src.document.domain.values import ApprovalStatus, DocumentId, ProcessingStatus
from src.document.infrastructure.minio_storage import MinioObjectStorage
from src.document.infrastructure.settings import DocumentSettings
from src.document.presentation.dependencies import CurrentPrincipal, get_current_principal
from src.document.presentation.routes import DocumentRouteServices, build_document_router


class Repository:
    def __init__(self) -> None:
        active = _document("00000000-0000-0000-0000-000000000001")
        self.documents = {
            active.id: active,
            DocumentId("00000000-0000-0000-0000-000000000002"): replace(
                active,
                id=DocumentId("00000000-0000-0000-0000-000000000002"),
                archived_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        }

    async def add(self, document: Document) -> Document:
        self.documents[document.id] = document
        return document

    async def list(self, query: object) -> tuple[Document, ...]:
        del query
        return tuple(document for document in self.documents.values() if document.archived_at is None)

    async def get(self, document_id: DocumentId) -> Document | None:
        return self.documents.get(document_id)

    async def archive(self, document_id: DocumentId, actor_id: str, archived_at: datetime) -> Document:
        document = self.documents[document_id].archive(actor_id, archived_at)
        self.documents[document_id] = document
        return document


class Storage:
    def __init__(self) -> None:
        self.presign_calls = 0
        self.put_calls: list[tuple[str, str, int, str]] = []
        self._adapter = MinioObjectStorage(
            self,
            DocumentSettings(
                enabled=True,
                database_url="postgresql+asyncpg://user:password@localhost:5432/documents",
                minio_endpoint="https://minio.test",
                bucket_name="documents",
                access_key="access-key",
                secret_key="secret-key",
            ),
        )

    async def upload(self, document_id: DocumentId, data: BytesIO, filename: str, content_type: str) -> StoredObject:
        return await self._adapter.upload(document_id, data, filename, content_type)

    async def remove(self, object_key: str) -> None:
        await self._adapter.remove(object_key)

    async def presign(self, document: Document) -> str:
        self.presign_calls += 1
        return f"https://download.invalid/{document.id.value}"

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str,
    ) -> None:
        del data
        self.put_calls.append((object_name, bucket_name, length, content_type))

    def remove_object(self, *, bucket_name: str, object_name: str) -> None:
        del bucket_name, object_name

    def presigned_get_object(self, *, bucket_name: str, object_name: str, expires: timedelta) -> str:
        del bucket_name, object_name, expires
        return "https://unused.invalid"


class Transaction:
    def __init__(self, repository: Repository) -> None:
        self.documents = repository

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        del exc_type, exc, traceback
        return False


class UnitOfWork:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def transaction(self) -> Transaction:
        return Transaction(self._repository)


def _document(identifier: str) -> Document:
    return Document(
        id=DocumentId(identifier),
        title="Policy",
        content_hash="hash",
        created_by="admin",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        approval_status=ApprovalStatus.DRAFT,
        processing_status=ProcessingStatus.NOT_STARTED,
        object_key="server/private",
        original_filename="policy.pdf",
        content_type="application/pdf",
        byte_size=7,
    )


@pytest.fixture
def app() -> tuple[FastAPI, Storage]:
    repository, storage = Repository(), Storage()
    services = DocumentRouteServices(
        CreateUploadedDocument(UnitOfWork(repository), storage),
        ListDocuments(repository),
        DetailDocument(repository),
        ArchiveDocument(repository),
        DownloadDocument(repository, storage),
    )
    application = FastAPI()
    application.include_router(build_document_router(services), prefix="/api/v1")
    return application, storage


async def _request(application: FastAPI, method: str, path: str, **kwargs: object):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_document_list_returns_401_for_anonymous_callers(app: tuple[FastAPI, Storage]) -> None:
    # Given
    application, _ = app
    # When
    response = await _request(application, "GET", "/api/v1/documents")
    # Then
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_advisor_can_read_but_cannot_mutate_and_archived_is_not_presigned(app: tuple[FastAPI, Storage]) -> None:
    # Given
    application, storage = app

    async def advisor() -> CurrentPrincipal:
        return CurrentPrincipal("advisor", Role.ADVISOR)

    application.dependency_overrides[get_current_principal] = advisor
    # When
    listed = await _request(application, "GET", "/api/v1/documents?page_size=100")
    detail = await _request(application, "GET", "/api/v1/documents/00000000-0000-0000-0000-000000000001")
    download = await _request(application, "GET", "/api/v1/documents/00000000-0000-0000-0000-000000000001/download")
    archived = await _request(application, "GET", "/api/v1/documents/00000000-0000-0000-0000-000000000002/download")
    created = await _request(
        application,
        "POST",
        "/api/v1/documents",
        data={"title": "P"},
        files={"file": ("p.pdf", b"x", "application/pdf")},
    )
    # Then
    assert listed.status_code == 200 and listed.json()["items"][0]["id"] == "00000000-0000-0000-0000-000000000001"
    assert detail.status_code == 200 and "object_key" not in detail.json()
    assert download.status_code == 200 and archived.status_code == 404 and storage.presign_calls == 1
    assert created.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_upload_archive_and_archived_document_is_hidden(app: tuple[FastAPI, Storage]) -> None:
    # Given
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    # When
    created = await _request(
        application,
        "POST",
        "/api/v1/documents",
        data={
            "title": "P",
            "description": "d",
            "document_type": "policy",
            "source_url": "https://source.example/policy",
        },
        files={"file": ("p.pdf", b"x", "application/pdf")},
    )
    identifier = created.json()["id"]
    archived = await _request(application, "POST", f"/api/v1/documents/{identifier}/archive")
    download = await _request(application, "GET", f"/api/v1/documents/{identifier}/download")
    # Then
    assert created.status_code == 201 and "object_key" not in created.json()
    assert created.json()["description"] == "d"
    assert created.json()["document_type"] == "policy"
    assert created.json()["source_url"] == "https://source.example/policy"
    assert archived.status_code == 200 and download.status_code == 404


@pytest.mark.asyncio
async def test_customer_can_read_but_cannot_mutate_documents(app: tuple[FastAPI, Storage]) -> None:
    # Given
    application, storage = app

    async def customer() -> CurrentPrincipal:
        return CurrentPrincipal("customer", Role.CUSTOMER)

    application.dependency_overrides[get_current_principal] = customer
    # When
    listed = await _request(application, "GET", "/api/v1/documents?page_size=100")
    detail = await _request(application, "GET", "/api/v1/documents/00000000-0000-0000-0000-000000000001")
    download = await _request(application, "GET", "/api/v1/documents/00000000-0000-0000-0000-000000000001/download")
    created = await _request(
        application,
        "POST",
        "/api/v1/documents",
        data={"title": "P"},
        files={"file": ("p.pdf", b"x", "application/pdf")},
    )
    archived = await _request(application, "POST", "/api/v1/documents/00000000-0000-0000-0000-000000000001/archive")
    # Then
    assert listed.status_code == 200 and listed.json()["items"][0]["id"] == "00000000-0000-0000-0000-000000000001"
    assert detail.status_code == 200 and "object_key" not in detail.json()
    assert download.status_code == 200 and storage.presign_calls == 1
    assert created.status_code == 403
    assert archived.status_code == 403


@pytest.mark.asyncio
async def test_document_upload_accepts_storage_only_csv_and_preserves_metadata(
    app: tuple[FastAPI, Storage],
) -> None:
    # Given
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    csv_content = b"name,amount\nAda,42\n"
    # When
    response = await _request(
        application,
        "POST",
        "/api/v1/documents",
        data={"title": "Report"},
        files={"file": ("report.csv", csv_content, "text/csv")},
    )
    # Then
    assert response.status_code == 201
    assert response.json()["original_filename"] == "report.csv"
    assert response.json()["content_type"] == "text/csv"
    assert response.json()["byte_size"] == len(csv_content)


@pytest.mark.asyncio
async def test_document_upload_rejects_image_files_after_separation(
    app: tuple[FastAPI, Storage],
) -> None:
    # Given
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    image_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    # When
    response = await _request(
        application,
        "POST",
        "/api/v1/documents",
        data={"title": "VF8 Image", "document_type": "VEHICLE_IMAGE"},
        files={"file": ("vf8.png", image_content, "image/png")},
    )
    # Then
    assert response.status_code == 415
    assert response.json() == {"detail": "document upload rejected"}


@pytest.mark.asyncio
async def test_document_upload_returns_413_when_file_exceeds_the_configured_limit(
    app: tuple[FastAPI, Storage],
) -> None:
    # Given
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    oversized_content = b"x" * (25 * 1024 * 1024 + 1)
    # When
    response = await _request(
        application,
        "POST",
        "/api/v1/documents",
        data={"title": "Oversized"},
        files={"file": ("oversized.pdf", oversized_content, "application/pdf")},
    )
    # Then
    assert response.status_code == 413
    assert response.json() == {"detail": "document upload rejected"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type"),
    (("unsupported.exe", "application/octet-stream"), ("mismatch.pdf", "text/plain")),
)
async def test_document_upload_returns_415_when_mime_or_extension_is_not_allowed(
    app: tuple[FastAPI, Storage], filename: str, content_type: str
) -> None:
    # Given
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    # When
    response = await _request(
        application,
        "POST",
        "/api/v1/documents",
        data={"title": "Rejected"},
        files={"file": (filename, b"x", content_type)},
    )
    # Then
    assert response.status_code == 415
    assert response.json() == {"detail": "document upload rejected"}


@pytest.mark.asyncio
async def test_document_upload_returns_stable_422_for_malformed_multipart(
    app: tuple[FastAPI, Storage],
) -> None:
    # Given
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    # When
    response = await _request(
        application,
        "POST",
        "/api/v1/documents",
        content=b"invalid",
        headers={"content-type": "multipart/form-data; boundary=bad"},
    )
    # Then
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid document request"}
