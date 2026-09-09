from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, BinaryIO, Protocol

from src.document.domain.entities import Document
from src.document.domain.values import DocumentId

if TYPE_CHECKING:
    from src.document.application.contracts import ListDocumentsQuery
    from src.document.application.policy_corpus import PolicyCorpusSummary
    from src.document.application.policy_notifications import PolicyNotificationRepository
    from src.document.domain.entities import VehicleDocument
    from src.document.domain.values import VehicleDocumentStatus


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Verified metadata calculated while storing a private object."""

    object_key: str
    content_hash: str
    content_type: str
    byte_size: int


class DocumentRepository(Protocol):
    """Document metadata persistence capability."""

    async def add(self, document: Document) -> Document: ...
    async def list(self, query: "ListDocumentsQuery") -> tuple[Document, ...]: ...
    async def get(self, document_id: DocumentId) -> Document | None: ...
    async def get_by_source_hash(self, source_url: str, content_hash: str) -> Document | None: ...
    async def get_latest_by_source_url(self, source_url: str) -> Document | None: ...
    async def archive(self, document_id: DocumentId, actor_id: str, archived_at: datetime) -> Document: ...


class VehicleDocumentRepository(Protocol):
    """Corpus RAG gan voi xe — docs/vehicle-catalog-schema.md muc 4.10.

    Tach khoi `DocumentRepository` vi day la chunk noi dung da chuan bi cho
    semantic search, khong phai file vat ly trong MinIO.
    """

    async def add(self, chunk: "VehicleDocument") -> "VehicleDocument": ...
    async def get(self, document_id: str) -> "VehicleDocument | None": ...
    async def list_for_vehicle(
        self, vehicle_id: str, *, status: "VehicleDocumentStatus | None" = None
    ) -> tuple["VehicleDocument", ...]: ...
    async def approve(self, document_id: str, actor_id: str, approved_at: datetime) -> "VehicleDocument | None": ...

    async def approve_for_source(
        self, source_document_id: str, actor_id: str, approved_at: datetime
    ) -> int: ...
    async def summary_for_source(self, source_document_id: str) -> "PolicyCorpusSummary": ...


class DocumentTransaction(Protocol):
    """Transaction-scoped Document repositories."""

    documents: DocumentRepository
    vehicle_documents: VehicleDocumentRepository
    policy_notifications: "PolicyNotificationRepository"


class DocumentUnitOfWork(Protocol):
    """Explicit transaction boundary for Document metadata writes."""

    def transaction(self) -> AbstractAsyncContextManager[DocumentTransaction]: ...


class ObjectStorage(Protocol):
    """Private binary storage capability used by Document application services."""

    async def upload(
        self,
        document_id: DocumentId,
        data: BinaryIO,
        filename: str,
        content_type: str,
    ) -> StoredObject: ...

    async def remove(self, object_key: str) -> None: ...

    async def read(self, object_key: str) -> bytes: ...

    async def presign(self, document: Document) -> str: ...
