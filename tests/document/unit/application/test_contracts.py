from datetime import datetime
from typing import Final

import pytest

from src.auth.domain.authorization import Role
from src.document.application.contracts import (
    ArchiveDocument,
    CreateDocument,
    DetailDocument,
    DownloadDocument,
    ListDocuments,
    ListDocumentsQuery,
)
from src.document.application.ports import DocumentRepository, ObjectStorage
from src.document.domain.entities import Document, DocumentMetadata
from src.document.domain.errors import InvalidPageSizeError
from src.document.domain.values import DocumentId


class MemoryRepository:
    def __init__(self) -> None:
        self.documents: list[Document] = []

    async def add(self, document: Document) -> Document:
        self.documents.append(document)
        return document

    async def list(self, query: ListDocumentsQuery) -> tuple[Document, ...]:
        ordered = sorted(self.documents, key=lambda item: (item.created_at, item.id.value), reverse=True)
        start = (query.page - 1) * query.page_size
        return tuple(ordered[start : start + query.page_size])

    async def get(self, document_id: DocumentId) -> Document | None:
        return next((item for item in self.documents if item.id == document_id), None)

    async def archive(self, document_id: DocumentId, actor_id: str, archived_at: datetime) -> Document:
        document = await self.get(document_id)
        if document is None:
            raise LookupError(document_id.value)
        archived = document.archive(actor_id, archived_at)
        self.documents = [archived if item.id == document_id else item for item in self.documents]
        return archived


class MemoryStorage:
    def __init__(self) -> None:
        self.presign_calls = 0

    async def presign(self, document: Document) -> str:
        self.presign_calls += 1
        return f"https://storage.test/{document.id.value}?ttl=60"


REPOSITORY: Final[type[DocumentRepository]] = MemoryRepository
STORAGE: Final[type[ObjectStorage]] = MemoryStorage


def test_list_query_bounds_page_size_and_declares_stable_ordering() -> None:
    query = ListDocumentsQuery(page=1, page_size=100)

    assert query.ordering == ("created_at", "desc", "id", "desc")
    with pytest.raises(InvalidPageSizeError):
        ListDocumentsQuery(page=1, page_size=101)


@pytest.mark.asyncio
async def test_application_contracts_create_list_detail_archive_download() -> None:
    repository = REPOSITORY()
    storage = STORAGE()
    created = await CreateDocument(repository).execute(
        metadata=DocumentMetadata(title="Policy", content_hash="hash"),
        actor_id="admin",
    )

    assert created.approval_status.value == "draft"
    assert await ListDocuments(repository).execute(ListDocumentsQuery(page=1, page_size=100)) == (created,)
    assert await DetailDocument(repository).execute(created.id) == created
    assert (
        await DownloadDocument(repository, storage).execute(
            created.id,
            actor_id="advisor",
            actor_role=Role.ADVISOR,
        )
    ).endswith("ttl=60")
    assert await ArchiveDocument(repository).execute(created.id, actor_id="admin") == await ArchiveDocument(
        repository
    ).execute(created.id, actor_id="admin")


@pytest.mark.asyncio
async def test_download_presigns_for_customer_when_document_exists() -> None:
    # Given
    repository = REPOSITORY()
    storage = STORAGE()
    document = await CreateDocument(repository).execute(
        metadata=DocumentMetadata(title="Policy", content_hash="hash"),
        actor_id="admin",
    )

    # When
    url = await DownloadDocument(repository, storage).execute(
        document.id,
        actor_id="customer",
        actor_role=Role.CUSTOMER,
    )

    # Then
    assert url.endswith("ttl=60")
    assert storage.presign_calls == 1


@pytest.mark.asyncio
async def test_download_raises_lookup_without_presigning_when_document_is_missing() -> None:
    # Given
    repository = REPOSITORY()
    storage = STORAGE()

    # When / Then
    with pytest.raises(LookupError):
        await DownloadDocument(repository, storage).execute(
            DocumentId("00000000-0000-0000-0000-000000000099"),
            actor_id="customer",
            actor_role=Role.CUSTOMER,
        )
    assert storage.presign_calls == 0
