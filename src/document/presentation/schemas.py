"""Typed request and response schemas for the Document HTTP boundary."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.document.application.policy_corpus import PolicyCorpusState, PolicyCorpusSummary
from src.document.application.policy_notifications import PolicyScopeApplicabilityUpdate
from src.document.domain.entities import Document
from src.document.domain.policy_notifications import PolicyNotification
from src.document.domain.policy_scopes import PolicyConflictResolution


class DocumentResponse(BaseModel):
    """Safe document metadata exposed to authenticated callers."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str | None
    document_type: str | None
    source_url: str | None
    source_authority: str
    source_revision: str | None
    source_published_at: datetime | None
    source_retrieved_at: datetime | None
    content_hash: str
    supersedes_document_id: str | None
    original_filename: str | None
    content_type: str | None
    byte_size: int | None
    approval_status: str
    processing_status: str
    created_at: datetime
    archived_at: datetime | None

    @classmethod
    def from_document(cls, document: Document) -> "DocumentResponse":
        """Convert domain metadata without exposing storage implementation fields."""
        return cls(
            id=document.id.value,
            title=document.title,
            description=document.description,
            document_type=document.document_type,
            source_url=document.source_url,
            source_authority=document.source_authority.value,
            source_revision=document.source_revision,
            source_published_at=document.source_published_at,
            source_retrieved_at=document.source_retrieved_at,
            content_hash=document.content_hash,
            supersedes_document_id=document.supersedes_document_id,
            original_filename=document.original_filename,
            content_type=document.content_type,
            byte_size=document.byte_size,
            approval_status=document.approval_status.value,
            processing_status=document.processing_status.value,
            created_at=document.created_at,
            archived_at=document.archived_at,
        )


class DocumentPageResponse(BaseModel):
    """Stable page of active documents."""

    model_config = ConfigDict(frozen=True)

    items: tuple[DocumentResponse, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class DownloadResponse(BaseModel):
    """Short-lived presigned URL with safe display metadata."""

    model_config = ConfigDict(frozen=True)

    url: str


class PolicyFactResponse(BaseModel):
    """Admin-visible structured fact and its direct evidence."""

    model_config = ConfigDict(frozen=True)
    label: str
    value: str
    evidence: str


class PolicyEvidenceResponse(BaseModel):
    """Admin-visible literal evidence from the source document."""

    model_config = ConfigDict(frozen=True)
    section: str | None
    quote: str


class ResolvedPolicyVehicleResponse(BaseModel):
    """Admin-safe vehicle identity resolved for authoritative chunks."""

    model_config = ConfigDict(frozen=True)
    vehicle_id: str
    slug: str
    display_name: str


class PolicyScopeResponse(BaseModel):
    """Structured applicability shown to the Admin before publication."""

    model_config = ConfigDict(frozen=True)
    scope_id: str
    policy_type: str
    topic: str
    vehicle_type: str
    component: str
    battery_chemistry: str | None
    ownership_model: str | None
    usage_type: str
    policy_active_from: date | None
    policy_active_to: date | None
    eligibility_basis: str
    eligibility_from: date | None
    eligibility_to: date | None
    is_current_default: bool
    affected_models: tuple[str, ...]
    resolved_vehicle_ids: tuple[str, ...]
    evidence_quotes: tuple[str, ...]
    status: str


class PolicyNotificationResponse(BaseModel):
    """Full analysis and draft state exposed only to Admin management routes."""

    model_config = ConfigDict(frozen=True)
    id: str
    source_document_id: str
    policy_type: str
    topic: str
    secondary_topics: tuple[str, ...]
    affected_models: tuple[str, ...]
    effective_from: date | None
    effective_to: date | None
    facts: tuple[PolicyFactResponse, ...]
    evidence: tuple[PolicyEvidenceResponse, ...]
    ai_confidence: float
    title: str
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    corpus_state: PolicyCorpusState
    corpus_chunk_count: int = Field(ge=0)
    resolved_vehicles: tuple[ResolvedPolicyVehicleResponse, ...]
    corpus_validation_errors: tuple[str, ...]
    scopes: tuple[PolicyScopeResponse, ...]

    @classmethod
    def from_notification(
        cls,
        notification: PolicyNotification,
        corpus: PolicyCorpusSummary | None = None,
    ) -> "PolicyNotificationResponse":
        """Map the aggregate without private object information."""
        summary = corpus or PolicyCorpusSummary(PolicyCorpusState.NOT_BUILT, 0)
        return cls(
            id=notification.id.value,
            source_document_id=notification.source_document_id.value,
            policy_type=notification.policy_type.value,
            topic=notification.topic.value,
            secondary_topics=tuple(item.value for item in notification.secondary_topics),
            affected_models=notification.affected_models,
            effective_from=notification.effective_from,
            effective_to=notification.effective_to,
            facts=tuple(
                PolicyFactResponse(label=item.label, value=item.value, evidence=item.evidence)
                for item in notification.facts
            ),
            evidence=tuple(
                PolicyEvidenceResponse(section=item.section, quote=item.quote)
                for item in notification.evidence
            ),
            ai_confidence=notification.ai_confidence,
            title=notification.title,
            content=notification.content,
            status=notification.status.value,
            created_at=notification.created_at,
            updated_at=notification.updated_at,
            published_at=notification.published_at,
            corpus_state=summary.state,
            corpus_chunk_count=summary.chunk_count,
            resolved_vehicles=tuple(
                ResolvedPolicyVehicleResponse(
                    vehicle_id=item.vehicle_id,
                    slug=item.slug,
                    display_name=item.display_name,
                )
                for item in summary.resolved_vehicles
            ),
            corpus_validation_errors=summary.validation_errors,
            scopes=tuple(
                PolicyScopeResponse(
                    scope_id=scope.id.value,
                    policy_type=scope.policy_type.value,
                    topic=scope.topic.value,
                    vehicle_type=scope.vehicle_type.value,
                    component=scope.component.value,
                    battery_chemistry=(
                        scope.battery_chemistry.value if scope.battery_chemistry else None
                    ),
                    ownership_model=(scope.ownership_model.value if scope.ownership_model else None),
                    usage_type=scope.usage_type.value,
                    policy_active_from=scope.policy_active_from,
                    policy_active_to=scope.policy_active_to,
                    eligibility_basis=scope.eligibility_basis.value,
                    eligibility_from=scope.eligibility_from,
                    eligibility_to=scope.eligibility_to,
                    is_current_default=scope.is_current_default,
                    affected_models=scope.affected_models,
                    resolved_vehicle_ids=scope.resolved_vehicle_ids,
                    evidence_quotes=scope.evidence_quotes,
                    status=scope.status.value,
                )
                for scope in notification.scopes
            ),
        )


class UpdatePolicyNotificationRequest(BaseModel):
    """Only fields a human reviewer may edit in the MVP."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=10_000)
    scopes: tuple[PolicyScopeApplicabilityUpdate, ...] | None = None


class PublishPolicyNotificationRequest(BaseModel):
    """Explicit Admin decision for an old/new revision conflict."""

    model_config = ConfigDict(extra="forbid")
    resolution: PolicyConflictResolution | None = None


class PublishedNotificationResponse(BaseModel):
    """Customer-safe published copy with safe source document reference."""

    model_config = ConfigDict(frozen=True)
    id: str
    title: str
    content: str
    affected_models: tuple[str, ...]
    effective_from: date | None
    effective_to: date | None
    published_at: datetime
    source_document_id: str | None = None

    @classmethod
    def from_notification(cls, notification: PolicyNotification) -> "PublishedNotificationResponse":
        """Map customer-facing publication fields."""
        if notification.published_at is None:
            raise ValueError("draft notification cannot be exposed to customers")
        return cls(
            id=notification.id.value,
            title=notification.title,
            content=notification.content,
            affected_models=notification.affected_models,
            effective_from=notification.effective_from,
            effective_to=notification.effective_to,
            published_at=notification.published_at,
            source_document_id=notification.source_document_id.value if notification.source_document_id else None,
        )


class PublishedNotificationPageResponse(BaseModel):
    """Simple stable customer notification page."""

    model_config = ConfigDict(frozen=True)
    items: tuple[PublishedNotificationResponse, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
