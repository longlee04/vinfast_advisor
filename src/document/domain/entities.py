from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from .errors import ArchivedDocumentError, InvalidTitleError
from .values import (
    ApprovalStatus,
    DocumentId,
    ProcessingStatus,
    SourceAuthority,
    VehicleDocumentStatus,
    ensure_processing_transition,
)


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    title: str
    content_hash: str
    description: str | None = None
    document_type: str | None = None
    source_url: str | None = None
    source_authority: SourceAuthority = SourceAuthority.UNKNOWN
    source_revision: str | None = None
    source_published_at: datetime | None = None
    source_retrieved_at: datetime | None = None
    source_etag: str | None = None
    source_last_modified: str | None = None
    supersedes_document_id: str | None = None
    original_filename: str | None = None
    object_key: str | None = None
    content_type: str | None = None
    byte_size: int | None = None


@dataclass(frozen=True, slots=True)
class Document:
    id: DocumentId
    title: str
    content_hash: str
    created_by: str
    created_at: datetime
    approval_status: ApprovalStatus
    processing_status: ProcessingStatus
    archived_at: datetime | None = None
    archived_by: str | None = None
    description: str | None = None
    document_type: str | None = None
    source_url: str | None = None
    source_authority: SourceAuthority = SourceAuthority.UNKNOWN
    source_revision: str | None = None
    source_published_at: datetime | None = None
    source_retrieved_at: datetime | None = None
    source_etag: str | None = None
    source_last_modified: str | None = None
    supersedes_document_id: str | None = None
    original_filename: str | None = None
    object_key: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(cls, metadata: DocumentMetadata, created_by: str) -> "Document":
        if not metadata.title.strip():
            raise InvalidTitleError()
        created_at = datetime.now(UTC)
        return cls(
            id=DocumentId(str(uuid4())),
            title=metadata.title,
            content_hash=metadata.content_hash,
            created_by=created_by,
            created_at=created_at,
            approval_status=ApprovalStatus.DRAFT,
            processing_status=ProcessingStatus.NOT_STARTED,
            description=metadata.description,
            document_type=metadata.document_type,
            source_url=metadata.source_url,
            source_authority=metadata.source_authority,
            source_revision=metadata.source_revision,
            source_published_at=metadata.source_published_at,
            source_retrieved_at=metadata.source_retrieved_at,
            source_etag=metadata.source_etag,
            source_last_modified=metadata.source_last_modified,
            supersedes_document_id=metadata.supersedes_document_id,
            original_filename=metadata.original_filename,
            object_key=metadata.object_key,
            content_type=metadata.content_type,
            byte_size=metadata.byte_size,
            updated_by=created_by,
            updated_at=created_at,
        )

    def archive(self, actor_id: str, archived_at: datetime) -> "Document":
        if self.archived_at is not None:
            return self
        return replace(self, archived_at=archived_at, archived_by=actor_id)

    def update_title(self, title: str) -> "Document":
        if self.archived_at is not None:
            raise ArchivedDocumentError(self.id)
        if not title.strip():
            raise InvalidTitleError()
        return replace(self, title=title)

    def transition_processing(self, status: ProcessingStatus) -> "Document":
        ensure_processing_transition(self.processing_status, status)
        return replace(self, processing_status=status)


@dataclass(frozen=True, slots=True)
class VehicleDocument:
    """RAG chunk cho catalog phương tiện — docs/vehicle-catalog-schema.md mục 4.10.

    Tách khỏi `Document` (file gốc tải lên) vì đây là nội dung đã chuẩn bị cho
    semantic search, gắn `vehicle_id` bên module product qua FK, không phải
    một file trong MinIO.
    """

    document_id: str
    document_type: str
    title: str
    content: str
    chunk_index: int
    status: VehicleDocumentStatus
    created_at: datetime
    updated_at: datetime
    vehicle_id: str | None = None
    policy_scope_id: str | None = None
    source_document_id: str | None = None
    source_content_hash: str | None = None
    source_revision: str | None = None
    section_title: str | None = None
    page_number: int | None = None
    source_url: str | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None
    embedding: list[float] | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    created_by: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
