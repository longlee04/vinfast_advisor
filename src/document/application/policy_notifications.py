"""Use cases and structured AI boundary for policy notification publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.document.application.errors import (
    DocumentTextTooLargeError,
    PolicyCorpusEmptyError,
    PolicySourceUnreviewedError,
)
from src.document.application.policy_corpus import PolicyCorpusBuilder
from src.document.application.ports import DocumentRepository, DocumentUnitOfWork, ObjectStorage
from src.document.domain.policy_notifications import (
    PolicyEvidence,
    PolicyFact,
    PolicyNotification,
    PolicyNotificationConflictError,
    PolicyNotificationId,
    PolicyNotificationStatus,
    PolicyTopic,
    PolicyType,
    normalized_policy_type,
)
from src.document.domain.policy_scopes import (
    BatteryChemistry,
    BatteryOwnershipModel,
    EligibilityBasis,
    InvalidPolicyScopeError,
    PolicyComponent,
    PolicyConflictResolution,
    PolicyScope,
    PolicyUsageType,
    PolicyVehicleType,
)
from src.document.domain.values import DocumentId, SourceAuthority

MAX_POLICY_TEXT_CHARACTERS = 120_000


class PolicyFactPayload(BaseModel):
    """Strict structured fact returned by the LLM."""

    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=300)
    value: str = Field(min_length=1, max_length=2_000)
    evidence: str = Field(min_length=1, max_length=4_000)


class PolicyEvidencePayload(BaseModel):
    """Strict source quote returned by the LLM."""

    model_config = ConfigDict(extra="forbid")
    section: str | None = Field(default=None, max_length=200)
    quote: str = Field(min_length=1, max_length=4_000)


class NotificationDraftPayload(BaseModel):
    """Customer-facing draft produced within the same LLM call."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=10_000)


class PolicyScopePayload(BaseModel):
    """One applicability cohort proposed by analysis and reviewed by an Admin."""

    model_config = ConfigDict(extra="forbid")
    policy_type: PolicyType
    topic: PolicyTopic
    vehicle_type: PolicyVehicleType
    component: PolicyComponent
    battery_chemistry: BatteryChemistry | None = None
    ownership_model: BatteryOwnershipModel | None = None
    usage_type: PolicyUsageType = PolicyUsageType.ANY
    policy_active_from: date | None = None
    policy_active_to: date | None = None
    eligibility_basis: EligibilityBasis = EligibilityBasis.NONE
    eligibility_from: date | None = None
    eligibility_to: date | None = None
    is_current_default: bool = False
    affected_models: list[str] = Field(default_factory=list, max_length=100)
    evidence_quotes: list[str] = Field(default_factory=list, max_length=100)


class PolicyScopeApplicabilityUpdate(BaseModel):
    """Admin-editable cohort fields; evidence and vehicle binding stay immutable."""

    model_config = ConfigDict(extra="forbid")
    scope_id: str
    ownership_model: BatteryOwnershipModel | None = None
    usage_type: PolicyUsageType
    policy_active_from: date | None = None
    policy_active_to: date | None = None
    eligibility_basis: EligibilityBasis
    eligibility_from: date | None = None
    eligibility_to: date | None = None
    is_current_default: bool = False


class PolicyAnalysisResult(BaseModel):
    """Pydantic v2 contract enforced at the external AI boundary."""

    model_config = ConfigDict(extra="forbid")
    policy_type: PolicyType
    topic: PolicyTopic
    secondary_topics: list[PolicyTopic] = Field(default_factory=list)
    affected_models: list[str] = Field(default_factory=list, max_length=100)
    effective_from: date | None = None
    effective_to: date | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    facts: list[PolicyFactPayload] = Field(default_factory=list, max_length=100)
    evidence: list[PolicyEvidencePayload] = Field(default_factory=list, max_length=100)
    scopes: list[PolicyScopePayload] = Field(default_factory=list, max_length=100)
    notification: NotificationDraftPayload

    @model_validator(mode="after")
    def enforce_topic_policy_boundary(self) -> PolicyAnalysisResult:
        """Correct obvious taxonomy contradictions before persistence."""
        self.policy_type = normalized_policy_type(self.policy_type, self.topic)
        return self


class PolicyTextExtractor(Protocol):
    """Supported-file text extraction capability."""

    async def extract(self, payload: bytes, *, filename: str, content_type: str) -> str: ...


class PolicyAnalyzer(Protocol):
    """Exactly one structured LLM request for one manual analysis."""

    async def analyze(self, *, title: str, text: str) -> PolicyAnalysisResult: ...


class PolicyNotificationRepository(Protocol):
    """Persistence operations needed by policy notification use cases."""

    async def get(self, notification_id: PolicyNotificationId) -> PolicyNotification | None: ...
    async def get_by_source(self, source_document_id: DocumentId) -> PolicyNotification | None: ...
    async def add(self, notification: PolicyNotification) -> PolicyNotification: ...
    async def save(self, notification: PolicyNotification) -> PolicyNotification: ...
    async def list_published(self, page: int, page_size: int) -> tuple[PolicyNotification, ...]: ...
    async def activate_scopes_for_source(
        self,
        source_document_id: str,
        actor_id: str,
        approved_at: datetime,
        resolution: PolicyConflictResolution | None = None,
    ) -> int: ...

    async def set_current_default(
        self,
        scope_id: str,
        actor_id: str,
        changed_at: datetime,
    ) -> PolicyScope: ...


@dataclass(frozen=True, slots=True)
class AnalyzePolicyDocument:
    """Read a private controlled source and persist one validated AI draft."""

    documents: DocumentRepository
    uow: DocumentUnitOfWork
    storage: ObjectStorage
    extractor: PolicyTextExtractor
    analyzer: PolicyAnalyzer
    corpus_builder: PolicyCorpusBuilder

    async def execute(self, document_id: DocumentId, actor_id: str) -> PolicyNotification:
        document = await self.documents.get(document_id)
        if document is None or document.archived_at is not None or document.object_key is None:
            raise LookupError(document_id.value)
        async with self.uow.transaction() as repositories:
            existing = await repositories.policy_notifications.get_by_source(document_id)
        if existing is not None:
            if existing.status is PolicyNotificationStatus.PUBLISHED:
                raise PolicyNotificationConflictError("published analysis is immutable")
            return existing

        payload = await self.storage.read(document.object_key)
        text = await self.extractor.extract(
            payload,
            filename=document.original_filename or "document",
            content_type=document.content_type or "application/octet-stream",
        )
        if len(text) > MAX_POLICY_TEXT_CHARACTERS:
            raise DocumentTextTooLargeError()
        result = PolicyAnalysisResult.model_validate(
            await self.analyzer.analyze(title=document.title, text=text)
        )
        notification = PolicyNotification.create_draft(
            source_document_id=document_id,
            policy_type=result.policy_type,
            topic=result.topic,
            secondary_topics=tuple(result.secondary_topics),
            affected_models=tuple(model.strip() for model in result.affected_models if model.strip()),
            effective_from=result.effective_from,
            effective_to=result.effective_to,
            facts=tuple(PolicyFact(item.label, item.value, item.evidence) for item in result.facts),
            evidence=tuple(PolicyEvidence(item.quote, item.section) for item in result.evidence),
            ai_confidence=result.confidence,
            title=result.notification.title,
            content=result.notification.content,
            actor_id=actor_id,
        )
        scope_payloads = result.scopes or [_legacy_scope_payload(result)]
        notification = notification.with_scopes(
            tuple(
                PolicyScope.create_draft(
                    notification_id=notification.id.value,
                    source_document_id=document_id.value,
                    policy_type=normalized_policy_type(item.policy_type, item.topic),
                    topic=item.topic,
                    vehicle_type=item.vehicle_type,
                    component=item.component,
                    battery_chemistry=item.battery_chemistry,
                    ownership_model=item.ownership_model,
                    usage_type=item.usage_type,
                    policy_active_from=item.policy_active_from,
                    policy_active_to=item.policy_active_to,
                    eligibility_basis=item.eligibility_basis,
                    eligibility_from=item.eligibility_from,
                    eligibility_to=item.eligibility_to,
                    is_current_default=item.is_current_default,
                    affected_models=tuple(
                        model.strip() for model in item.affected_models if model.strip()
                    ),
                    evidence_quotes=tuple(
                        quote.strip() for quote in item.evidence_quotes if quote.strip()
                    ),
                    actor_id=actor_id,
                )
                for item in scope_payloads
            )
        )
        drafts = await self.corpus_builder.build_drafts(document, notification, text)
        async with self.uow.transaction() as repositories:
            persisted = await repositories.policy_notifications.add(notification)
            for chunk in drafts:
                await repositories.vehicle_documents.add(chunk)
            return persisted


def _legacy_scope_payload(result: PolicyAnalysisResult) -> PolicyScopePayload:
    """Keep an old analyzer response reviewable without inventing customer cohorts."""
    if result.topic is PolicyTopic.VEHICLE_WARRANTY:
        component = PolicyComponent.VEHICLE
    elif result.topic is PolicyTopic.SPARE_PART_WARRANTY:
        component = PolicyComponent.SPARE_PART
    elif result.topic is PolicyTopic.BATTERY_WARRANTY:
        component = PolicyComponent.HIGH_VOLTAGE_BATTERY
    else:
        component = PolicyComponent.BATTERY_SERVICE
    return PolicyScopePayload(
        policy_type=result.policy_type,
        topic=result.topic,
        vehicle_type=PolicyVehicleType.CAR,
        component=component,
        policy_active_from=result.effective_from,
        policy_active_to=result.effective_to,
        is_current_default=True,
        affected_models=result.affected_models,
        evidence_quotes=[item.quote for item in result.evidence],
    )


@dataclass(frozen=True, slots=True)
class UpdatePolicyNotificationDraft:
    """Persist an Admin's title/content edits without changing AI audit fields."""

    uow: DocumentUnitOfWork

    async def execute(
        self,
        notification_id: PolicyNotificationId,
        *,
        actor_id: str,
        title: str,
        content: str,
        scopes: tuple[PolicyScopeApplicabilityUpdate, ...] | None = None,
    ) -> PolicyNotification:
        del actor_id
        async with self.uow.transaction() as repositories:
            current = await repositories.policy_notifications.get(notification_id)
            if current is None:
                raise LookupError(notification_id.value)
            updated = current.edit(title=title, content=content)
            if scopes is not None:
                updates = {item.scope_id: item for item in scopes}
                if set(updates) != {item.id.value for item in current.scopes}:
                    raise PolicyNotificationConflictError("scope set cannot change during review")
                updated = updated.with_scopes(
                    tuple(
                        scope.edit_applicability(
                            ownership_model=updates[scope.id.value].ownership_model,
                            usage_type=updates[scope.id.value].usage_type,
                            policy_active_from=updates[scope.id.value].policy_active_from,
                            policy_active_to=updates[scope.id.value].policy_active_to,
                            eligibility_basis=updates[scope.id.value].eligibility_basis,
                            eligibility_from=updates[scope.id.value].eligibility_from,
                            eligibility_to=updates[scope.id.value].eligibility_to,
                            is_current_default=updates[scope.id.value].is_current_default,
                        )
                        for scope in current.scopes
                    )
                )
            return await repositories.policy_notifications.save(updated)


@dataclass(frozen=True, slots=True)
class PublishPolicyNotification:
    """Perform the only transition that can make a notification customer-visible."""

    uow: DocumentUnitOfWork

    async def execute(
        self,
        notification_id: PolicyNotificationId,
        actor_id: str,
        resolution: PolicyConflictResolution | None = None,
    ) -> PolicyNotification:
        if resolution is PolicyConflictResolution.CANCEL:
            raise PolicyNotificationConflictError("policy publication was cancelled")
        async with self.uow.transaction() as repositories:
            current = await repositories.policy_notifications.get(notification_id)
            if current is None:
                raise LookupError(notification_id.value)
            was_published = current.status is PolicyNotificationStatus.PUBLISHED
            source = await repositories.documents.get(current.source_document_id)
            if (
                source is None
                or not source.source_url
                or source.source_authority is SourceAuthority.UNKNOWN
            ):
                raise PolicySourceUnreviewedError()
            if not was_published:
                corpus = await repositories.vehicle_documents.summary_for_source(
                    current.source_document_id.value
                )
                if corpus.chunk_count == 0 or corpus.validation_errors:
                    raise PolicyCorpusEmptyError()
                try:
                    activated_scopes = (
                        await repositories.policy_notifications.activate_scopes_for_source(
                            current.source_document_id.value,
                            actor_id,
                            datetime.now(UTC),
                            resolution,
                        )
                    )
                except InvalidPolicyScopeError as error:
                    raise PolicyCorpusEmptyError() from error
                if activated_scopes == 0:
                    raise PolicyCorpusEmptyError()
                current = await repositories.policy_notifications.get(notification_id)
                if current is None:
                    raise LookupError(notification_id.value)
            published = await repositories.policy_notifications.save(current.publish(actor_id))
            approved = await repositories.vehicle_documents.approve_for_source(
                current.source_document_id.value,
                actor_id,
                published.published_at or published.updated_at,
            )
            if not was_published and approved == 0:
                raise PolicyCorpusEmptyError()
            return published


@dataclass(frozen=True, slots=True)
class SetCurrentPolicyDefault:
    """Select one already ACTIVE revision as default without deleting historical evidence."""

    uow: DocumentUnitOfWork

    async def execute(self, scope_id: str, actor_id: str) -> PolicyScope:
        async with self.uow.transaction() as repositories:
            return await repositories.policy_notifications.set_current_default(
                scope_id,
                actor_id,
                datetime.now(UTC),
            )


@dataclass(frozen=True, slots=True)
class ListPublishedPolicyNotifications:
    """Return only explicitly published notifications in stable newest-first order."""

    repository: PolicyNotificationRepository

    async def execute(self, *, page: int, page_size: int) -> tuple[PolicyNotification, ...]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("invalid pagination")
        return await self.repository.list_published(page, page_size)
