"""Real PostgreSQL and MinIO Document MVP flow contract."""

from contextlib import asynccontextmanager
from hashlib import sha256
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.auth.domain.authorization import Role
from src.document.application.contracts import CreateUploadedDocument, UploadDocumentCommand
from src.document.application.errors import DocumentPersistenceError
from src.document.domain.entities import Document
from src.document.infrastructure.minio_storage import MinioObjectStorage
from src.document.infrastructure.settings import DocumentSettings
from src.document.presentation.dependencies import CurrentPrincipal, get_current_principal

PDF_BYTES = b"%PDF-1.4\nreal-document-flow\n"


@pytest.mark.asyncio
async def test_document_mvp_full_flow_when_real_services_are_available(
    document_app: FastAPI,
    document_engine: AsyncEngine,
    document_bucket_name: str,
    minio_client: Minio,
) -> None:
    """Persist one private object, permit Advisor reads, and retain archived data."""

    # Given
    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin-1", Role.ADMIN)

    document_app.dependency_overrides[get_current_principal] = admin

    # When
    async with AsyncClient(transport=ASGITransport(app=document_app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/documents",
            data={"title": "Operating policy"},
            files={"file": ("policy.pdf", PDF_BYTES, "application/pdf")},
        )

    # Then
    assert created.status_code == 201
    document_id = created.json()["id"]
    async with document_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT content_hash, byte_size, content_type, object_key, approval_status, "
                    "processing_status, archived_at FROM documents WHERE id = :document_id"
                ),
                {"document_id": document_id},
            )
        ).one()
    assert row.content_hash == sha256(PDF_BYTES).hexdigest()
    assert row.byte_size == len(PDF_BYTES)
    assert row.content_type == "application/pdf"
    assert row.approval_status == "draft"
    assert row.processing_status == "not_started"
    assert row.archived_at is None
    object_key = str(row.object_key)
    metadata = minio_client.stat_object(document_bucket_name, object_key)
    assert metadata.content_type == "application/pdf"
    response = minio_client.get_object(document_bucket_name, object_key)
    try:
        assert response.read() == PDF_BYTES
    finally:
        response.close()
        response.release_conn()

    async def advisor() -> CurrentPrincipal:
        return CurrentPrincipal("advisor-1", Role.ADVISOR)

    document_app.dependency_overrides[get_current_principal] = advisor
    async with AsyncClient(transport=ASGITransport(app=document_app), base_url="http://test") as client:
        listed = await client.get("/api/v1/documents")
        detailed = await client.get(f"/api/v1/documents/{document_id}")
        downloaded = await client.get(f"/api/v1/documents/{document_id}/download")

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [document_id]
    assert detailed.status_code == 200
    assert detailed.json()["id"] == document_id
    assert downloaded.status_code == 200
    assert parse_qs(urlsplit(downloaded.json()["url"]).query)["X-Amz-Expires"] == ["60"]

    document_app.dependency_overrides[get_current_principal] = admin
    async with AsyncClient(transport=ASGITransport(app=document_app), base_url="http://test") as client:
        archived = await client.post(f"/api/v1/documents/{document_id}/archive")
        active_documents = await client.get("/api/v1/documents")
        rejected_download = await client.get(f"/api/v1/documents/{document_id}/download")

    assert archived.status_code == 200
    assert active_documents.json()["items"] == []
    assert rejected_download.status_code == 404
    async with document_engine.connect() as connection:
        retained = await connection.scalar(
            text("SELECT archived_at IS NOT NULL FROM documents WHERE id = :document_id"),
            {"document_id": document_id},
        )
    assert retained is True
    assert minio_client.stat_object(document_bucket_name, object_key).size == len(PDF_BYTES)


@pytest.mark.asyncio
async def test_upload_removes_real_minio_object_when_postgres_commit_fails(
    document_bucket_name: str,
    minio_client: Minio,
) -> None:
    # Given
    settings = DocumentSettings(
        enabled=True,
        database_url="postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth",
        minio_endpoint="http://localhost:9000",
        bucket_name=document_bucket_name,
        access_key="p150_minio",
        secret_key="p150_minio_test_secret",
    )
    storage = MinioObjectStorage(minio_client, settings)
    object_keys_before = {item.object_name for item in minio_client.list_objects(document_bucket_name, recursive=True)}

    class FailingUnitOfWork:
        @asynccontextmanager
        async def transaction(self):
            yield type("Repositories", (), {"documents": type("Documents", (), {"add": self._fail})()})()

        async def _fail(self, document: Document) -> Document:
            del document
            raise DocumentPersistenceError()

    upload = CreateUploadedDocument(FailingUnitOfWork(), storage)

    # When
    with pytest.raises(DocumentPersistenceError):
        await upload.execute(
            UploadDocumentCommand(
                title="Compensation policy",
                actor_id="admin-1",
                data=BytesIO(PDF_BYTES),
                filename="compensation.pdf",
                content_type="application/pdf",
            )
        )

    # Then
    object_keys_after = {item.object_name for item in minio_client.list_objects(document_bucket_name, recursive=True)}
    assert object_keys_after == object_keys_before
