"""Policy notification MVP application behavior."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Self

import pytest

from src.document.application.errors import (
    DocumentTextUnavailableError,
    PolicyCorpusEmptyError,
    PolicySourceUnreviewedError,
)
from src.document.application.policy_notifications import (
    AnalyzePolicyDocument,
    ListPublishedPolicyNotifications,
    NotificationDraftPayload,
    PolicyAnalysisResult,
    PolicyEvidencePayload,
    PolicyFactPayload,
    PolicyScopeApplicabilityUpdate,
    PublishPolicyNotification,
    UpdatePolicyNotificationDraft,
)
from src.document.domain.entities import Document, VehicleDocument
from src.document.domain.policy_notifications import (
    PolicyNotification,
    PolicyNotificationConflictError,
    PolicyNotificationId,
    PolicyNotificationStatus,
    PolicyTopic,
    PolicyType,
)
from src.document.domain.policy_scopes import (
    EligibilityBasis,
    PolicyConflictResolution,
    PolicyUsageType,
)
from src.document.domain.values import (
    ApprovalStatus,
    DocumentId,
    ProcessingStatus,
    SourceAuthority,
    VehicleDocumentStatus,
)


def _document() -> Document:
    return Document(
        id=DocumentId("00000000-0000-0000-0000-000000000001"),
        title="Chính sách bảo hành pin VF7",
        content_hash="hash",
        created_by="admin",
        created_at=datetime(2026, 8, 27, tzinfo=UTC),
        approval_status=ApprovalStatus.DRAFT,
        processing_status=ProcessingStatus.NOT_STARTED,
        source_url="https://vinfastauto.com/vn_vi/thong-tin-bao-hanh",
        source_authority=SourceAuthority.OFFICIAL,
        object_key="documents/policy.pdf",
        original_filename="policy.pdf",
        content_type="application/pdf",
    )


def _analysis(
    *,
    policy_type: PolicyType = PolicyType.BATTERY_POLICY,
    topic: PolicyTopic = PolicyTopic.BATTERY_WARRANTY,
) -> PolicyAnalysisResult:
    return PolicyAnalysisResult(
        policy_type=policy_type,
        topic=topic,
        affected_models=["VF7"],
        effective_from=date(2026, 9, 1),
        confidence=0.96,
        facts=[
            PolicyFactPayload(
                label="Thời hạn bảo hành pin",
                value="8 năm hoặc 160.000 km",
                evidence="Pin VF7 được bảo hành 8 năm hoặc 160.000 km.",
            )
        ],
        evidence=[
            PolicyEvidencePayload(
                section="3.2",
                quote="Pin VF7 được bảo hành 8 năm hoặc 160.000 km.",
            )
        ],
        notification=NotificationDraftPayload(
            title="Cập nhật chính sách bảo hành pin VF7",
            content="Từ 01/09/2026, VF7 áp dụng chính sách bảo hành pin.",
        ),
    )


class MemoryRepository:
    def __init__(self) -> None:
        self.document = _document()
        self.notifications: dict[str, PolicyNotification] = {}

    async def get(self, identifier: DocumentId | PolicyNotificationId):
        if isinstance(identifier, DocumentId):
            return self.document if identifier == self.document.id else None
        return self.notifications.get(identifier.value)

    async def get_by_source(self, source_document_id: DocumentId) -> PolicyNotification | None:
        return next(
            (
                item
                for item in self.notifications.values()
                if item.source_document_id == source_document_id
            ),
            None,
        )

    async def add(self, notification: PolicyNotification) -> PolicyNotification:
        self.notifications[notification.id.value] = notification
        return notification

    async def save(self, notification: PolicyNotification) -> PolicyNotification:
        self.notifications[notification.id.value] = notification
        return notification

    async def list_published(self, page: int, page_size: int) -> tuple[PolicyNotification, ...]:
        del page, page_size
        return tuple(
            item
            for item in self.notifications.values()
            if item.status is PolicyNotificationStatus.PUBLISHED
        )

    async def activate_scopes_for_source(
        self,
        source_document_id: str,
        actor_id: str,
        approved_at: datetime,
        resolution: PolicyConflictResolution | None = None,
    ) -> int:
        del resolution
        notification = next(
            item
            for item in self.notifications.values()
            if item.source_document_id.value == source_document_id
        )
        vehicle_ids = tuple(
            chunk.vehicle_id
            for chunk in getattr(self, "vehicle_documents", ())
            if chunk.vehicle_id is not None
        )
        scopes = tuple(
            scope.with_resolved_vehicles(vehicle_ids or ("00000000-0000-0000-0000-000000000007",)).activate(
                actor_id, approved_at
            )
            for scope in notification.scopes
        )
        self.notifications[notification.id.value] = notification.with_scopes(scopes)
        return len(scopes)


class MemoryVehicleDocuments:
    def __init__(self) -> None:
        self.chunks: dict[str, VehicleDocument] = {}

    async def add(self, chunk: VehicleDocument) -> VehicleDocument:
        self.chunks[chunk.document_id] = chunk
        return chunk

    async def summary_for_source(self, source_document_id: str):  # noqa: ANN201
        from src.document.application.policy_corpus import PolicyCorpusState, PolicyCorpusSummary

        chunks = [
            chunk for chunk in self.chunks.values() if chunk.source_document_id == source_document_id
        ]
        validation_errors = tuple(
            "Embedding policy chưa sẵn sàng hoặc sai phiên bản."
            for chunk in chunks
            if chunk.embedding is None or len(chunk.embedding) != 1024
        )
        return PolicyCorpusSummary(
            PolicyCorpusState.DRAFT if chunks else PolicyCorpusState.NOT_BUILT,
            len(chunks),
            validation_errors=validation_errors,
        )

    async def approve_for_source(
        self, source_document_id: str, actor_id: str, approved_at: datetime
    ) -> int:
        approved = 0
        for document_id, chunk in tuple(self.chunks.items()):
            if (
                chunk.source_document_id != source_document_id
                or chunk.status is not VehicleDocumentStatus.DRAFT
            ):
                continue
            self.chunks[document_id] = replace(
                chunk,
                status=VehicleDocumentStatus.ACTIVE,
                approved_by=actor_id,
                approved_at=approved_at,
                updated_at=approved_at,
            )
            approved += 1
        return approved


class CorpusBuilder:
    async def build_drafts(
        self,
        document: Document,
        notification: PolicyNotification,
        source_text: str,
    ) -> tuple[VehicleDocument, ...]:
        assert notification.evidence[0].quote in source_text
        moment = datetime(2026, 8, 27, tzinfo=UTC)
        return (
            VehicleDocument(
                document_id="00000000-0000-0000-0000-000000000099",
                vehicle_id="00000000-0000-0000-0000-000000000007",
                policy_scope_id=notification.scopes[0].id.value,
                source_document_id=document.id.value,
                source_content_hash=document.content_hash,
                source_revision=document.content_hash[:40],
                document_type="WARRANTY_POLICY",
                title=notification.title,
                content=notification.evidence[0].quote,
                chunk_index=0,
                section_title=notification.topic.value.upper(),
                source_url=document.source_url,
                embedding_model="test",
                embedding_version="test-v1",
                embedding=[0.1] * 1024,
                status=VehicleDocumentStatus.DRAFT,
                created_by=notification.created_by,
                created_at=moment,
                updated_at=moment,
            ),
        )


@dataclass
class Transaction(AbstractAsyncContextManager):
    documents: MemoryRepository
    policy_notifications: MemoryRepository
    vehicle_documents: MemoryVehicleDocuments

    async def __aenter__(self) -> Self:
        self._notification_snapshot = dict(self.policy_notifications.notifications)
        self._chunk_snapshot = dict(self.vehicle_documents.chunks)
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is not None:
            self.policy_notifications.notifications = self._notification_snapshot
            self.vehicle_documents.chunks = self._chunk_snapshot
        return False


class UnitOfWork:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository
        self.vehicle_documents = MemoryVehicleDocuments()

    def transaction(self) -> Transaction:
        return Transaction(self.repository, self.repository, self.vehicle_documents)


class Storage:
    async def read(self, object_key: str) -> bytes:
        assert object_key == "documents/policy.pdf"
        return b"stored bytes"


class Extractor:
    async def extract(self, payload: bytes, *, filename: str, content_type: str) -> str:
        assert payload == b"stored bytes"
        assert filename == "policy.pdf"
        assert content_type == "application/pdf"
        return "Pin VF7 được bảo hành 8 năm hoặc 160.000 km."


class Analyzer:
    def __init__(self, result: PolicyAnalysisResult) -> None:
        self.result = result
        self.calls = 0

    async def analyze(self, *, title: str, text: str) -> PolicyAnalysisResult:
        assert title and text
        self.calls += 1
        return self.result


class EmptyExtractor:
    async def extract(self, payload: bytes, *, filename: str, content_type: str) -> str:
        del payload, filename, content_type
        raise DocumentTextUnavailableError()


@pytest.mark.asyncio
async def test_battery_warranty_is_deterministically_normalized_to_warranty_policy() -> None:
    repository = MemoryRepository()
    analyzer = Analyzer(_analysis())
    use_case = AnalyzePolicyDocument(
        repository,
        UnitOfWork(repository),
        Storage(),
        Extractor(),
        analyzer,
        CorpusBuilder(),
    )

    notification = await use_case.execute(repository.document.id, "admin-1")

    assert analyzer.calls == 1
    assert notification.policy_type is PolicyType.WARRANTY_POLICY
    assert notification.topic is PolicyTopic.BATTERY_WARRANTY
    assert notification.status is PolicyNotificationStatus.DRAFT
    assert await use_case.execute(repository.document.id, "admin-1") == notification
    assert analyzer.calls == 1


@pytest.mark.parametrize(
    ("topic", "reported_type", "expected_type"),
    [
        (PolicyTopic.BATTERY_RENTAL, PolicyType.UNKNOWN, PolicyType.BATTERY_POLICY),
        (PolicyTopic.PROMOTION, PolicyType.OTHER_POLICY, PolicyType.PROMOTION_POLICY),
        (PolicyTopic.VEHICLE_PRICE, PolicyType.UNKNOWN, PolicyType.PRICE_POLICY),
    ],
)
def test_closed_topics_are_mapped_to_deterministic_policy_types(
    topic: PolicyTopic,
    reported_type: PolicyType,
    expected_type: PolicyType,
) -> None:
    result = _analysis(policy_type=reported_type, topic=topic)

    assert result.policy_type is expected_type


@pytest.mark.asyncio
async def test_empty_or_scanned_source_does_not_call_ai_or_persist_a_draft() -> None:
    repository = MemoryRepository()
    analyzer = Analyzer(_analysis())
    use_case = AnalyzePolicyDocument(
        repository,
        UnitOfWork(repository),
        Storage(),
        EmptyExtractor(),
        analyzer,
        CorpusBuilder(),
    )

    with pytest.raises(DocumentTextUnavailableError):
        await use_case.execute(repository.document.id, "admin-1")

    assert analyzer.calls == 0
    assert repository.notifications == {}


@pytest.mark.asyncio
async def test_admin_edit_is_the_copy_published_to_customers() -> None:
    repository = MemoryRepository()
    uow = UnitOfWork(repository)
    created = await AnalyzePolicyDocument(
        repository, uow, Storage(), Extractor(), Analyzer(_analysis()), CorpusBuilder()
    ).execute(repository.document.id, "admin-1")
    [draft_chunk] = uow.vehicle_documents.chunks.values()
    assert draft_chunk.status is VehicleDocumentStatus.DRAFT
    assert await ListPublishedPolicyNotifications(repository).execute(page=1, page_size=20) == ()

    edited = await UpdatePolicyNotificationDraft(uow).execute(
        created.id,
        actor_id="admin-1",
        title="Bảo hành pin VF7 từ tháng 9",
        content="VF7 được bảo hành pin 8 năm hoặc 160.000 km.",
    )
    published = await PublishPolicyNotification(uow).execute(edited.id, "admin-1")
    customer_items = await ListPublishedPolicyNotifications(repository).execute(page=1, page_size=20)

    assert published.status is PolicyNotificationStatus.PUBLISHED
    [active_chunk] = uow.vehicle_documents.chunks.values()
    assert active_chunk.status is VehicleDocumentStatus.ACTIVE
    assert active_chunk.approved_by == "admin-1"
    assert customer_items[0].title == "Bảo hành pin VF7 từ tháng 9"
    assert customer_items[0].content == "VF7 được bảo hành pin 8 năm hoặc 160.000 km."


@pytest.mark.asyncio
async def test_admin_can_review_cohort_without_rewriting_evidence_or_vehicle_binding() -> None:
    repository = MemoryRepository()
    uow = UnitOfWork(repository)
    created = await AnalyzePolicyDocument(
        repository, uow, Storage(), Extractor(), Analyzer(_analysis()), CorpusBuilder()
    ).execute(repository.document.id, "admin-1")
    scope = created.scopes[0]

    updated = await UpdatePolicyNotificationDraft(uow).execute(
        created.id,
        actor_id="admin-1",
        title=created.title,
        content=created.content,
        scopes=(
            PolicyScopeApplicabilityUpdate(
                scope_id=scope.id.value,
                ownership_model=None,
                usage_type=PolicyUsageType.ANY,
                eligibility_basis=EligibilityBasis.INVOICE_DATE,
                eligibility_from=date(2025, 8, 16),
                eligibility_to=None,
                is_current_default=True,
            ),
        ),
    )

    assert updated.scopes[0].eligibility_basis is EligibilityBasis.INVOICE_DATE
    assert updated.scopes[0].eligibility_from == date(2025, 8, 16)
    assert updated.scopes[0].evidence_quotes == scope.evidence_quotes
    assert updated.scopes[0].affected_models == scope.affected_models


@pytest.mark.asyncio
async def test_published_notification_cannot_be_edited_or_reanalyzed() -> None:
    repository = MemoryRepository()
    uow = UnitOfWork(repository)
    use_case = AnalyzePolicyDocument(
        repository, uow, Storage(), Extractor(), Analyzer(_analysis()), CorpusBuilder()
    )
    created = await use_case.execute(repository.document.id, "admin-1")
    await PublishPolicyNotification(uow).execute(created.id, "admin-1")

    with pytest.raises(PolicyNotificationConflictError):
        await UpdatePolicyNotificationDraft(uow).execute(
            created.id,
            actor_id="admin-1",
            title="Không được sửa",
            content="Không được sửa",
        )
    with pytest.raises(PolicyNotificationConflictError):
        await use_case.execute(repository.document.id, "admin-1")


@pytest.mark.asyncio
async def test_publish_rolls_back_notification_when_source_corpus_is_missing() -> None:
    repository = MemoryRepository()
    uow = UnitOfWork(repository)
    created = await AnalyzePolicyDocument(
        repository, uow, Storage(), Extractor(), Analyzer(_analysis()), CorpusBuilder()
    ).execute(repository.document.id, "admin-1")
    uow.vehicle_documents.chunks.clear()

    with pytest.raises(PolicyCorpusEmptyError):
        await PublishPolicyNotification(uow).execute(created.id, "admin-1")

    persisted = repository.notifications[created.id.value]
    assert persisted.status is PolicyNotificationStatus.DRAFT
    assert persisted.published_at is None and persisted.published_by is None


@pytest.mark.asyncio
async def test_publish_rejects_chunk_without_schema_compatible_embedding() -> None:
    repository = MemoryRepository()
    uow = UnitOfWork(repository)
    created = await AnalyzePolicyDocument(
        repository, uow, Storage(), Extractor(), Analyzer(_analysis()), CorpusBuilder()
    ).execute(repository.document.id, "admin-1")
    chunk_id, chunk = next(iter(uow.vehicle_documents.chunks.items()))
    uow.vehicle_documents.chunks[chunk_id] = replace(chunk, embedding=None)

    with pytest.raises(PolicyCorpusEmptyError):
        await PublishPolicyNotification(uow).execute(created.id, "admin-1")

    assert repository.notifications[created.id.value].status is PolicyNotificationStatus.DRAFT


@pytest.mark.asyncio
async def test_unknown_source_authority_cannot_be_published() -> None:
    repository = MemoryRepository()
    repository.document = replace(repository.document, source_authority=SourceAuthority.UNKNOWN)
    uow = UnitOfWork(repository)
    created = await AnalyzePolicyDocument(
        repository, uow, Storage(), Extractor(), Analyzer(_analysis()), CorpusBuilder()
    ).execute(repository.document.id, "admin-1")

    with pytest.raises(PolicySourceUnreviewedError):
        await PublishPolicyNotification(uow).execute(created.id, "admin-1")

    assert repository.notifications[created.id.value].status is PolicyNotificationStatus.DRAFT


@pytest.mark.asyncio
async def test_admin_cancel_decision_keeps_draft_and_corpus_inactive() -> None:
    repository = MemoryRepository()
    uow = UnitOfWork(repository)
    created = await AnalyzePolicyDocument(
        repository, uow, Storage(), Extractor(), Analyzer(_analysis()), CorpusBuilder()
    ).execute(repository.document.id, "admin-1")

    with pytest.raises(PolicyNotificationConflictError):
        await PublishPolicyNotification(uow).execute(
            created.id,
            "admin-1",
            PolicyConflictResolution.CANCEL,
        )

    assert repository.notifications[created.id.value].status is PolicyNotificationStatus.DRAFT
    assert all(
        chunk.status is VehicleDocumentStatus.DRAFT
        for chunk in uow.vehicle_documents.chunks.values()
    )
