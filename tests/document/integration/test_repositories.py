"""Document PostgreSQL repository contract tests."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.document.application.contracts import ListDocumentsQuery
from src.document.domain.entities import Document, VehicleDocument
from src.document.domain.errors import DocumentDomainError
from src.document.domain.policy_notifications import (
    PolicyEvidence,
    PolicyFact,
    PolicyNotification,
    PolicyNotificationConflictError,
    PolicyTopic,
    PolicyType,
)
from src.document.domain.policy_scopes import (
    EligibilityBasis,
    PolicyComponent,
    PolicyConflictResolution,
    PolicyScope,
    PolicyScopeStatus,
    PolicyUsageType,
    PolicyVehicleType,
)
from src.document.domain.values import (
    ApprovalStatus,
    DocumentId,
    ProcessingStatus,
    VehicleDocumentStatus,
)
from src.document.infrastructure.repositories import DocumentUnitOfWork
from tests.support.postgres_test_database import (
    TemporaryPostgresDatabase,
    assert_connection_uses_temporary_database,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def engine(
    document_database: TemporaryPostgresDatabase,
) -> AsyncIterator[AsyncEngine]:
    created = create_async_engine(document_database.database_url)
    try:
        yield created
    finally:
        await created.dispose()


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
    document_database: TemporaryPostgresDatabase,
) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as connection:
        await assert_connection_uses_temporary_database(connection, document_database)
        await connection.execute(text("TRUNCATE TABLE vehicle_documents, documents CASCADE"))
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def uow(session_factory: async_sessionmaker[AsyncSession]) -> DocumentUnitOfWork:
    return DocumentUnitOfWork(session_factory)


def make_document(*, title: str = "Policy", content_hash: str = "a" * 64, seconds: int = 0) -> Document:
    return Document(
        id=DocumentId(str(uuid4())),
        title=title,
        content_hash=content_hash,
        created_by="admin-1",
        created_at=NOW + timedelta(seconds=seconds),
        approval_status=ApprovalStatus.DRAFT,
        processing_status=ProcessingStatus.NOT_STARTED,
        description="Internal policy",
        document_type="policy",
        source_url="https://example.test/policy",
        original_filename="policy.pdf",
        object_key="documents/server-owned.pdf",
        content_type="application/pdf",
        byte_size=1024,
        updated_by="admin-1",
        updated_at=NOW + timedelta(seconds=seconds),
    )


class TestDocumentRepository:
    def test_rejects_non_mvp_ordering_when_constructed(self) -> None:
        # Given
        # When
        with pytest.raises(DocumentDomainError):
            ListDocumentsQuery(page=1, page_size=100, ordering=("title", "asc", "id", "desc"))

        # Then

    @pytest.mark.asyncio
    async def test_round_trips_mvp_metadata_when_committed(self, uow: DocumentUnitOfWork) -> None:
        # Given
        document = make_document()

        # When
        async with uow.transaction() as repositories:
            await repositories.documents.add(document)
        async with uow.transaction() as repositories:
            loaded = await repositories.documents.get(document.id)

        # Then
        assert loaded == document

    @pytest.mark.asyncio
    async def test_rolls_back_write_when_transaction_exits_with_exception(self, uow: DocumentUnitOfWork) -> None:
        # Given
        document = make_document()

        # When
        with pytest.raises(RuntimeError, match="force rollback"):
            async with uow.transaction() as repositories:
                await repositories.documents.add(document)
                raise RuntimeError("force rollback")
        async with uow.transaction() as repositories:
            loaded = await repositories.documents.get(document.id)

        # Then
        assert loaded is None

    @pytest.mark.asyncio
    async def test_allows_duplicate_content_hashes_when_committed(self, uow: DocumentUnitOfWork) -> None:
        # Given
        first = make_document(title="First")
        second = make_document(title="Second")

        # When
        async with uow.transaction() as repositories:
            await repositories.documents.add(first)
            await repositories.documents.add(second)

        # Then
        async with uow.transaction() as repositories:
            result = await repositories.documents.list(ListDocumentsQuery(page=1, page_size=100))
        assert {document.id for document in result} == {first.id, second.id}

    @pytest.mark.asyncio
    async def test_lists_active_documents_newest_then_id_and_excludes_archived(self, uow: DocumentUnitOfWork) -> None:
        # Given
        older = make_document(title="Older", seconds=1)
        newer_a = make_document(title="Newer A", seconds=2)
        newer_b = make_document(title="Newer B", seconds=2)
        async with uow.transaction() as repositories:
            for document in (older, newer_a, newer_b):
                await repositories.documents.add(document)
            await repositories.documents.archive(older.id, "admin-2", NOW + timedelta(minutes=1))

        # When
        async with uow.transaction() as repositories:
            result = await repositories.documents.list(ListDocumentsQuery(page=1, page_size=100))

        # Then
        assert result == tuple(sorted((newer_a, newer_b), key=lambda item: item.id.value, reverse=True))

    @pytest.mark.asyncio
    async def test_archive_is_idempotent_when_repeated(self, uow: DocumentUnitOfWork) -> None:
        # Given
        document = make_document()
        async with uow.transaction() as repositories:
            await repositories.documents.add(document)

        # When
        async with uow.transaction() as repositories:
            first = await repositories.documents.archive(document.id, "admin-2", NOW)
        async with uow.transaction() as repositories:
            second = await repositories.documents.archive(document.id, "admin-3", NOW + timedelta(minutes=1))

        # Then
        assert second == first
        assert first.archived_by == "admin-2"


def make_policy_notification(document_id: DocumentId) -> PolicyNotification:
    """Create a complete draft aggregate for repository round trips."""
    return PolicyNotification.create_draft(
        source_document_id=document_id,
        policy_type=PolicyType.WARRANTY_POLICY,
        topic=PolicyTopic.BATTERY_WARRANTY,
        secondary_topics=(),
        affected_models=("VF7",),
        effective_from=date(2026, 9, 1),
        effective_to=None,
        facts=(PolicyFact("Thời hạn", "8 năm", "Pin VF7 được bảo hành 8 năm."),),
        evidence=(PolicyEvidence("Pin VF7 được bảo hành 8 năm.", "3.2"),),
        ai_confidence=0.96,
        title="Bản nháp",
        content="Nội dung bản nháp",
        actor_id="admin-1",
    )


@pytest.mark.asyncio
async def test_policy_notification_round_trip_hides_draft_then_lists_edited_publication(
    uow: DocumentUnitOfWork,
) -> None:
    document = make_document()
    draft = make_policy_notification(document.id)
    async with uow.transaction() as repositories:
        await repositories.documents.add(document)
        await repositories.policy_notifications.add(draft)

    async with uow.transaction() as repositories:
        assert await repositories.policy_notifications.list_published(1, 20) == ()
        loaded = await repositories.policy_notifications.get(draft.id)
        assert loaded is not None
        approved = loaded.edit(title="Admin duyệt", content="Nội dung Admin duyệt").publish("admin-1")
        await repositories.policy_notifications.save(approved)

    async with uow.transaction() as repositories:
        published = await repositories.policy_notifications.list_published(1, 20)
    assert published == (approved,)


@pytest.mark.asyncio
async def test_policy_notification_enforces_one_analysis_per_source_document(
    uow: DocumentUnitOfWork,
) -> None:
    document = make_document()
    first = make_policy_notification(document.id)
    second = make_policy_notification(document.id)
    async with uow.transaction() as repositories:
        await repositories.documents.add(document)
        await repositories.policy_notifications.add(first)

    with pytest.raises(PolicyNotificationConflictError):
        async with uow.transaction() as repositories:
            await repositories.policy_notifications.add(second)


@pytest.mark.asyncio
async def test_policy_notification_round_trips_multiple_review_scopes(
    uow: DocumentUnitOfWork,
) -> None:
    document = make_document()
    notification = make_policy_notification(document.id)
    scopes = (
        PolicyScope.create_draft(
            notification_id=notification.id.value,
            source_document_id=document.id.value,
            policy_type=PolicyType.WARRANTY_POLICY,
            topic=PolicyTopic.VEHICLE_WARRANTY,
            vehicle_type=PolicyVehicleType.MOTORBIKE,
            component=PolicyComponent.VEHICLE,
            usage_type=PolicyUsageType.ANY,
            eligibility_basis=EligibilityBasis.INVOICE_DATE,
            eligibility_from=date(2025, 8, 16),
            eligibility_to=None,
            affected_models=("Feliz S",),
            evidence_quotes=("Xe được bảo hành 6 năm.",),
            actor_id="admin-1",
            is_current_default=True,
        ),
        PolicyScope.create_draft(
            notification_id=notification.id.value,
            source_document_id=document.id.value,
            policy_type=PolicyType.WARRANTY_POLICY,
            topic=PolicyTopic.BATTERY_WARRANTY,
            vehicle_type=PolicyVehicleType.MOTORBIKE,
            component=PolicyComponent.LFP_BATTERY,
            usage_type=PolicyUsageType.ANY,
            eligibility_basis=EligibilityBasis.INVOICE_DATE,
            eligibility_from=date(2025, 8, 16),
            eligibility_to=None,
            affected_models=("Feliz S",),
            evidence_quotes=("Pin được bảo hành 8 năm.",),
            actor_id="admin-1",
            is_current_default=True,
        ),
    )
    notification = notification.with_scopes(scopes)

    async with uow.transaction() as repositories:
        await repositories.documents.add(document)
        await repositories.policy_notifications.add(notification)

    async with uow.transaction() as repositories:
        loaded = await repositories.policy_notifications.get(notification.id)

    assert loaded is not None
    assert {scope.id.value: scope for scope in loaded.scopes} == {
        scope.id.value: scope for scope in scopes
    }


@pytest.mark.asyncio
async def test_policy_scope_publish_requires_explicit_supersede_and_closes_old_cohort(
    uow: DocumentUnitOfWork,
    engine: AsyncEngine,
) -> None:
    vehicle_id = str(uuid4())
    model_name = f"Policy Conflict {vehicle_id[:8]}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO vehicles (
                    vehicle_id, vehicle_type, brand, model_name, status, slug, created_at, updated_at
                ) VALUES (
                    :vehicle_id, 'ELECTRIC_MOTORBIKE', 'VinFast', :model_name, 'ACTIVE',
                    :slug, :now, :now
                )
                """
            ),
            {
                "vehicle_id": vehicle_id,
                "model_name": model_name,
                "slug": f"policy-conflict-{vehicle_id}",
                "now": NOW,
            },
        )

    old_document = make_document(title="Old policy", content_hash="b" * 64)
    new_document = make_document(title="New policy", content_hash="c" * 64)
    old_notification = make_policy_notification(old_document.id)
    new_notification = make_policy_notification(new_document.id)
    old_scope = PolicyScope.create_draft(
        notification_id=old_notification.id.value,
        source_document_id=old_document.id.value,
        policy_type=PolicyType.WARRANTY_POLICY,
        topic=PolicyTopic.BATTERY_WARRANTY,
        vehicle_type=PolicyVehicleType.MOTORBIKE,
        component=PolicyComponent.LFP_BATTERY,
        usage_type=PolicyUsageType.ANY,
        eligibility_basis=EligibilityBasis.INVOICE_DATE,
        eligibility_from=date(2024, 1, 1),
        eligibility_to=None,
        affected_models=("Feliz S",),
        evidence_quotes=("Pin LFP duoc bao hanh 5 nam.",),
        actor_id="admin-1",
        is_current_default=True,
    )
    new_scope = PolicyScope.create_draft(
        notification_id=new_notification.id.value,
        source_document_id=new_document.id.value,
        policy_type=PolicyType.WARRANTY_POLICY,
        topic=PolicyTopic.BATTERY_WARRANTY,
        vehicle_type=PolicyVehicleType.MOTORBIKE,
        component=PolicyComponent.LFP_BATTERY,
        usage_type=PolicyUsageType.ANY,
        eligibility_basis=EligibilityBasis.INVOICE_DATE,
        eligibility_from=date(2025, 8, 16),
        eligibility_to=None,
        affected_models=("Feliz S",),
        evidence_quotes=("Pin LFP duoc bao hanh 8 nam.",),
        actor_id="admin-1",
        is_current_default=True,
    )
    old_notification = old_notification.with_scopes((old_scope,))
    new_notification = new_notification.with_scopes((new_scope,))

    def chunk_for(document: Document, scope: PolicyScope, content: str) -> VehicleDocument:
        return VehicleDocument(
            document_id=str(uuid4()),
            vehicle_id=vehicle_id,
            policy_scope_id=scope.id.value,
            source_document_id=document.id.value,
            source_content_hash=document.content_hash,
            source_revision=document.content_hash[:40],
            document_type="WARRANTY_POLICY",
            title=document.title,
            content=content,
            chunk_index=0,
            section_title="BATTERY_WARRANTY",
            source_url=document.source_url,
            status=VehicleDocumentStatus.DRAFT,
            created_by="admin-1",
            created_at=NOW,
            updated_at=NOW,
        )

    async with uow.transaction() as repositories:
        await repositories.documents.add(old_document)
        await repositories.documents.add(new_document)
        await repositories.policy_notifications.add(old_notification)
        await repositories.policy_notifications.add(new_notification)
        await repositories.vehicle_documents.add(
            chunk_for(old_document, old_scope, "Pin LFP duoc bao hanh 5 nam.")
        )
        await repositories.vehicle_documents.add(
            chunk_for(new_document, new_scope, "Pin LFP duoc bao hanh 8 nam.")
        )
        assert (
            await repositories.policy_notifications.activate_scopes_for_source(
                old_document.id.value, "admin-1", NOW
            )
            == 1
        )

    with pytest.raises(PolicyNotificationConflictError):
        async with uow.transaction() as repositories:
            await repositories.policy_notifications.activate_scopes_for_source(
                new_document.id.value, "admin-2", NOW + timedelta(minutes=1)
            )

    async with uow.transaction() as repositories:
        assert (
            await repositories.policy_notifications.activate_scopes_for_source(
                new_document.id.value,
                "admin-2",
                NOW + timedelta(minutes=1),
                PolicyConflictResolution.SUPERSEDE_DEFAULT,
            )
            == 1
        )
        loaded_old = await repositories.policy_notifications.get(old_notification.id)
        loaded_new = await repositories.policy_notifications.get(new_notification.id)

    assert loaded_old is not None and loaded_new is not None
    assert loaded_old.scopes[0].status is PolicyScopeStatus.ACTIVE
    assert loaded_old.scopes[0].eligibility_to == date(2025, 8, 15)
    assert loaded_old.scopes[0].is_current_default is False
    assert loaded_new.scopes[0].status is PolicyScopeStatus.ACTIVE
    assert loaded_new.scopes[0].supersedes_scope_id == old_scope.id.value

    async with uow.transaction() as repositories:
        restored = await repositories.policy_notifications.set_current_default(
            old_scope.id.value,
            "admin-rollback",
            NOW + timedelta(minutes=2),
        )
        after_old = await repositories.policy_notifications.get(old_notification.id)
        after_new = await repositories.policy_notifications.get(new_notification.id)

    assert restored.is_current_default is True
    assert after_old is not None and after_old.scopes[0].is_current_default is True
    assert after_new is not None and after_new.scopes[0].is_current_default is False


@pytest.mark.asyncio
async def test_policy_chunks_keep_embeddings_draft_until_source_publication(
    uow: DocumentUnitOfWork,
) -> None:
    source = make_document()
    chunk = VehicleDocument(
        document_id=str(uuid4()),
        source_document_id=source.id.value,
        source_content_hash=source.content_hash,
        source_revision=source.content_hash[:40],
        document_type="WARRANTY_POLICY",
        title="Bảo hành VF7",
        content="Pin VF7 được bảo hành 8 năm hoặc 160.000 km.",
        chunk_index=0,
        section_title="BATTERY_WARRANTY:3.2",
        source_url=source.source_url,
        embedding_model="test-embedding",
        embedding_version="test-v1",
        embedding=[0.125] * 1024,
        status=VehicleDocumentStatus.DRAFT,
        valid_from=NOW,
        valid_to=NOW + timedelta(days=365),
        created_by="admin-1",
        created_at=NOW,
        updated_at=NOW,
    )
    async with uow.transaction() as repositories:
        await repositories.documents.add(source)
        await repositories.vehicle_documents.add(chunk)

    async with uow.transaction() as repositories:
        loaded = await repositories.vehicle_documents.get(chunk.document_id)
        draft_summary = await repositories.vehicle_documents.summary_for_source(source.id.value)
        approved = await repositories.vehicle_documents.approve_for_source(
            source.id.value, "admin-2", NOW + timedelta(minutes=1)
        )
        activated = await repositories.vehicle_documents.get(chunk.document_id)
        active_summary = await repositories.vehicle_documents.summary_for_source(source.id.value)

    assert loaded is not None and loaded.status is VehicleDocumentStatus.DRAFT
    assert loaded.embedding == [0.125] * 1024
    assert draft_summary.state.value == "DRAFT" and draft_summary.chunk_count == 1
    assert approved == 1
    assert activated is not None and activated.status is VehicleDocumentStatus.ACTIVE
    assert activated.approved_by == "admin-2"
    assert active_summary.state.value == "ACTIVE" and active_summary.chunk_count == 1
