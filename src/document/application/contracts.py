from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import BinaryIO

from src.auth.domain.authorization import Action, Role, authorize
from src.document.application.errors import (
    DocumentPersistenceError,
    DocumentStorageUnavailableError,
    DocumentUploadRejectedError,
)
from src.document.application.policy_sources import UnsafePolicySourceError, validate_official_source_url
from src.document.application.ports import DocumentRepository, DocumentUnitOfWork, ObjectStorage
from src.document.domain.entities import Document, DocumentMetadata
from src.document.domain.errors import InvalidDocumentOrderingError, InvalidPageSizeError
from src.document.domain.values import DocumentId, SourceAuthority


@dataclass(frozen=True, slots=True)
class ListDocumentsQuery:
    page: int
    page_size: int
    ordering: tuple[str, str, str, str] = ("created_at", "desc", "id", "desc")

    def __post_init__(self) -> None:
        if self.page < 1 or not 1 <= self.page_size <= 100:
            raise InvalidPageSizeError(self.page_size)
        if self.ordering != ("created_at", "desc", "id", "desc"):
            raise InvalidDocumentOrderingError(self.ordering)


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    """Typed application input for a single client-provided upload stream."""

    title: str
    actor_id: str
    data: BinaryIO
    filename: str
    content_type: str
    description: str | None = None
    document_type: str | None = None
    source_url: str | None = None
    source_authority: SourceAuthority = SourceAuthority.UNKNOWN
    source_revision: str | None = None


@dataclass(frozen=True, slots=True)
class CreateUploadedDocument:
    """Coordinates object upload then metadata persistence with compensation."""

    uow: DocumentUnitOfWork
    storage: ObjectStorage

    async def execute(self, command: UploadDocumentCommand) -> Document:
        """Upload one object, persist its calculated metadata, or compensate."""
        if command.source_authority is SourceAuthority.OFFICIAL:
            if not command.source_url:
                raise DocumentUploadRejectedError(status_code=422)
            try:
                validate_official_source_url(command.source_url)
            except UnsafePolicySourceError as error:
                raise DocumentUploadRejectedError(status_code=422) from error
        provisional = Document.create(
            DocumentMetadata(
                title=command.title,
                content_hash="",
                description=command.description,
                document_type=command.document_type,
                source_url=command.source_url,
                source_authority=command.source_authority,
                source_revision=command.source_revision,
            ),
            command.actor_id,
        )
        stored = await self.storage.upload(
            provisional.id,
            command.data,
            command.filename,
            command.content_type,
        )
        document = replace(
            provisional,
            content_hash=stored.content_hash,
            original_filename=command.filename,
            object_key=stored.object_key,
            content_type=stored.content_type,
            byte_size=stored.byte_size,
        )
        try:
            async with self.uow.transaction() as repositories:
                return await repositories.documents.add(document)
        except DocumentPersistenceError:
            await self._compensate(stored.object_key)
            raise
        except Exception as error:
            await self._compensate(stored.object_key)
            raise DocumentPersistenceError() from error

    async def _compensate(self, object_key: str) -> None:
        """Attempt cleanup while preserving the database failure as the outcome."""
        try:
            await self.storage.remove(object_key)
        except DocumentStorageUnavailableError:
            return


@dataclass(frozen=True, slots=True)
class CreateDocument:
    repository: DocumentRepository

    async def execute(self, metadata: DocumentMetadata, actor_id: str) -> Document:
        return await self.repository.add(Document.create(metadata, actor_id))


@dataclass(frozen=True, slots=True)
class ListDocuments:
    repository: DocumentRepository

    async def execute(self, query: ListDocumentsQuery) -> tuple[Document, ...]:
        return await self.repository.list(query)


@dataclass(frozen=True, slots=True)
class DetailDocument:
    repository: DocumentRepository

    async def execute(self, document_id: DocumentId) -> Document | None:
        return await self.repository.get(document_id)


@dataclass(frozen=True, slots=True)
class ArchiveDocument:
    repository: DocumentRepository

    async def execute(self, document_id: DocumentId, actor_id: str) -> Document:
        return await self.repository.archive(document_id, actor_id, datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class DownloadDocument:
    repository: DocumentRepository
    storage: ObjectStorage

    async def execute(self, document_id: DocumentId, actor_id: str, actor_role: Role) -> str:
        authorize(actor_role, Action.READ_DOCUMENT, actor_id=actor_id)
        document = await self.repository.get(document_id)
        if document is None or document.archived_at is not None:
            raise LookupError(document_id.value)
        return await self.storage.presign(document)
