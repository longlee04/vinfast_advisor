"""SQLAlchemy persistence model owned exclusively by the Document module."""

from datetime import date, datetime
from typing import Final

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

IDENTIFIER_LENGTH: Final[int] = 64
TITLE_LENGTH: Final[int] = 500
TYPE_LENGTH: Final[int] = 100
FILENAME_LENGTH: Final[int] = 512
OBJECT_KEY_LENGTH: Final[int] = 1024
CONTENT_TYPE_LENGTH: Final[int] = 255
HASH_LENGTH: Final[int] = 128
VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS: Final[int] = 1024


class DocumentBase(DeclarativeBase):
    """Declarative base containing Document-owned tables only."""


class DocumentRow(DocumentBase):
    """Mutable ORM row required by SQLAlchemy.  # noqa: MUTABLE_OK"""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    title: Mapped[str] = mapped_column(String(TITLE_LENGTH), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(TYPE_LENGTH), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_authority: Mapped[str] = mapped_column(String(24), nullable=False, server_default="UNKNOWN")
    source_revision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supersedes_document_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    original_filename: Mapped[str | None] = mapped_column(String(FILENAME_LENGTH), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(OBJECT_KEY_LENGTH), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(CONTENT_TYPE_LENGTH), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    approval_status: Mapped[str] = mapped_column(String(TYPE_LENGTH), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(TYPE_LENGTH), nullable=False)
    created_by: Mapped[str] = mapped_column(String(IDENTIFIER_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(title) > 0", name="ck_documents_title_present"),
        CheckConstraint("byte_size IS NULL OR byte_size >= 0", name="ck_documents_byte_size_non_negative"),
        CheckConstraint("approval_status IN ('draft')", name="ck_documents_approval_status"),
        CheckConstraint(
            "source_authority IN ('OFFICIAL', 'INTERNAL_APPROVED', 'UNKNOWN')",
            name="ck_documents_source_authority",
        ),
        CheckConstraint(
            "processing_status IN ('not_started', 'queued', 'processing', 'completed', 'failed')",
            name="ck_documents_processing_status",
        ),
        Index("ix_documents_active", "archived_at", postgresql_where=text("archived_at IS NULL")),
        Index("ix_documents_created_desc", "created_at", "id"),
        Index("ix_documents_source_revision", "source_url", "source_revision"),
        Index(
            "uq_documents_source_hash",
            "source_url",
            "content_hash",
            unique=True,
            postgresql_where=text(
                "source_url IS NOT NULL AND source_authority IN ('OFFICIAL', 'INTERNAL_APPROVED')"
            ),
        ),
    )


class PolicyNotificationRow(DocumentBase):
    """One AI analysis, editable draft, and explicit publication aggregate."""

    __tablename__ = "policy_notifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    policy_type: Mapped[str] = mapped_column(String(40), nullable=False)
    topic: Mapped[str] = mapped_column(String(40), nullable=False)
    secondary_topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    affected_models: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    facts: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[list[dict[str, str | None]]] = mapped_column(JSONB, nullable=False, default=list)
    ai_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[str] = mapped_column(String(TITLE_LENGTH), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    created_by: Mapped[str] = mapped_column(String(IDENTIFIER_LENGTH), nullable=False)
    published_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="ck_policy_notifications_status"),
        CheckConstraint(
            "ai_confidence >= 0 AND ai_confidence <= 1",
            name="ck_policy_notifications_confidence",
        ),
        CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(content)) > 0",
            name="ck_policy_notifications_copy_present",
        ),
        CheckConstraint(
            "status = 'draft' OR (published_by IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_policy_notifications_publication_actor",
        ),
        Index("ix_policy_notifications_status_published", "status", "published_at", "id"),
        Index("ix_policy_notifications_created", "created_at", "id"),
    )


class VehicleDocumentRow(DocumentBase):
    """Corpus RAG cho catalog phương tiện — theo docs/vehicle-catalog-schema.md mục 4.10.

    Tách khỏi `DocumentRow` (file gốc do người dùng tải lên) vì đây là chunk
    nội dung đã chuẩn bị cho semantic search, gắn với `vehicle_id` bên module
    product, không phải một file vật lý trong MinIO.
    """

    __tablename__ = "vehicle_documents"

    document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vehicle_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    policy_scope_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("policy_scopes.scope_id", ondelete="SET NULL"), nullable=True
    )
    source_document_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    source_content_hash: Mapped[str | None] = mapped_column(String(HASH_LENGTH), nullable=True)
    source_revision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    embedding: Mapped[list | None] = mapped_column(Vector(VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS), nullable=True)
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(section_title, '') || ' ' || content)",
            persisted=True,
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'ARCHIVED')", name="ck_vehicle_documents_status"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_vehicle_documents_period",
        ),
        CheckConstraint("length(trim(content)) > 0", name="ck_vehicle_documents_content"),
        CheckConstraint(
            "status <> 'ACTIVE' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_vehicle_documents_approval",
        ),
        Index("ix_vehicle_documents_scope", "vehicle_id", "status", "document_type", "valid_from", "valid_to"),
        Index("ix_vehicle_documents_source_document", "source_document_id"),
        Index("ix_vehicle_documents_policy_scope", "policy_scope_id", "status", "document_type"),
        Index("ix_vehicle_documents_content_tsv", "content_tsv", postgresql_using="gin"),
        Index(
            "ix_vehicle_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class PolicyScopeRow(DocumentBase):
    """Reviewed applicability metadata used before ranking policy chunks."""

    __tablename__ = "policy_scopes"

    scope_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    notification_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("policy_notifications.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    policy_type: Mapped[str] = mapped_column(String(40), nullable=False)
    topic: Mapped[str] = mapped_column(String(40), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(20), nullable=False)
    component: Mapped[str] = mapped_column(String(40), nullable=False)
    battery_chemistry: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ownership_model: Mapped[str | None] = mapped_column(String(24), nullable=True)
    usage_type: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_active_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    policy_active_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    eligibility_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    eligibility_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    eligibility_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current_default: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    supersedes_scope_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("policy_scopes.scope_id", ondelete="SET NULL"), nullable=True
    )
    affected_models: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    resolved_vehicle_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence_quotes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name="ck_policy_scopes_status"),
        CheckConstraint(
            "eligibility_to IS NULL OR eligibility_from IS NULL OR eligibility_to >= eligibility_from",
            name="ck_policy_scopes_eligibility_period",
        ),
        CheckConstraint(
            "policy_active_to IS NULL OR policy_active_from IS NULL OR policy_active_to >= policy_active_from",
            name="ck_policy_scopes_active_period",
        ),
        CheckConstraint(
            "eligibility_basis <> 'NONE' OR (eligibility_from IS NULL AND eligibility_to IS NULL)",
            name="ck_policy_scopes_eligibility_basis",
        ),
        Index("ix_policy_scopes_source", "source_document_id", "status"),
        Index(
            "ix_policy_scopes_applicability",
            "vehicle_type",
            "topic",
            "component",
            "status",
            "is_current_default",
        ),
    )
