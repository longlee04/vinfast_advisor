"""Async SQLAlchemy repository and explicit transaction boundary for Documents."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.document.application.contracts import ListDocumentsQuery
from src.document.application.policy_corpus import (
    PolicyCorpusState,
    PolicyCorpusSummary,
    ResolvedPolicyVehicle,
)
from src.document.domain.entities import Document, VehicleDocument
from src.document.domain.policy_notifications import (
    PolicyEvidence,
    PolicyFact,
    PolicyNotification,
    PolicyNotificationConflictError,
    PolicyNotificationId,
    PolicyNotificationStatus,
    PolicyTopic,
    PolicyType,
)
from src.document.domain.policy_scopes import (
    BatteryChemistry,
    BatteryOwnershipModel,
    EligibilityBasis,
    PolicyComponent,
    PolicyConflictResolution,
    PolicyScope,
    PolicyScopeId,
    PolicyScopeStatus,
    PolicyUsageType,
    PolicyVehicleType,
)
from src.document.domain.values import (
    ApprovalStatus,
    DocumentId,
    ProcessingStatus,
    SourceAuthority,
    VehicleDocumentStatus,
)
from src.document.infrastructure.models import (
    DocumentRow,
    PolicyNotificationRow,
    PolicyScopeRow,
    VehicleDocumentRow,
)
from src.products.infrastructure.models import VehicleRow


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


def _to_document(row: DocumentRow) -> Document:
    return Document(
        id=DocumentId(row.id),
        title=row.title,
        content_hash=row.content_hash,
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        approval_status=ApprovalStatus(row.approval_status),
        processing_status=ProcessingStatus(row.processing_status),
        archived_at=_utc(row.archived_at) if row.archived_at else None,
        archived_by=row.archived_by,
        description=row.description,
        document_type=row.document_type,
        source_url=row.source_url,
        source_authority=SourceAuthority(row.source_authority),
        source_revision=row.source_revision,
        source_published_at=_utc(row.source_published_at) if row.source_published_at else None,
        source_retrieved_at=_utc(row.source_retrieved_at) if row.source_retrieved_at else None,
        source_etag=row.source_etag,
        source_last_modified=row.source_last_modified,
        supersedes_document_id=row.supersedes_document_id,
        original_filename=row.original_filename,
        object_key=row.object_key,
        content_type=row.content_type,
        byte_size=row.byte_size,
        updated_by=row.updated_by,
        updated_at=_utc(row.updated_at),
    )


def _vehicle_document_to_row_values(chunk: VehicleDocument) -> dict:
    """Entity -> dict cot. Bo `content_tsv` vi do la GENERATED column."""
    return {
        "document_id": chunk.document_id,
        "vehicle_id": chunk.vehicle_id,
        "policy_scope_id": chunk.policy_scope_id,
        "source_document_id": chunk.source_document_id,
        "source_content_hash": chunk.source_content_hash,
        "source_revision": chunk.source_revision,
        "document_type": chunk.document_type,
        "title": chunk.title,
        "content": chunk.content,
        "chunk_index": chunk.chunk_index,
        "section_title": chunk.section_title,
        "page_number": chunk.page_number,
        "source_url": chunk.source_url,
        "embedding_model": chunk.embedding_model,
        "embedding_version": chunk.embedding_version,
        "embedding": chunk.embedding,
        "status": chunk.status.value,
        "valid_from": chunk.valid_from,
        "valid_to": chunk.valid_to,
        "created_by": chunk.created_by,
        "approved_by": chunk.approved_by,
        "approved_at": chunk.approved_at,
        "created_at": chunk.created_at,
        "updated_at": chunk.updated_at,
    }


def _vehicle_document_to_entity(row) -> VehicleDocument:  # noqa: ANN001
    return VehicleDocument(
        document_id=row.document_id,
        document_type=row.document_type,
        title=row.title,
        content=row.content,
        chunk_index=row.chunk_index,
        status=VehicleDocumentStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        vehicle_id=row.vehicle_id,
        policy_scope_id=row.policy_scope_id,
        source_document_id=row.source_document_id,
        source_content_hash=row.source_content_hash,
        source_revision=row.source_revision,
        section_title=row.section_title,
        page_number=row.page_number,
        source_url=row.source_url,
        embedding_model=row.embedding_model,
        embedding_version=row.embedding_version,
        embedding=list(row.embedding) if row.embedding is not None else None,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        created_by=row.created_by,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
    )


def _policy_notification_to_entity(
    row: PolicyNotificationRow, scopes: tuple[PolicyScope, ...] = ()
) -> PolicyNotification:
    return PolicyNotification(
        id=PolicyNotificationId(row.id),
        source_document_id=DocumentId(row.source_document_id),
        policy_type=PolicyType(row.policy_type),
        topic=PolicyTopic(row.topic),
        secondary_topics=tuple(PolicyTopic(value) for value in row.secondary_topics),
        affected_models=tuple(row.affected_models),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        facts=tuple(PolicyFact(**item) for item in row.facts),
        evidence=tuple(PolicyEvidence(**item) for item in row.evidence),
        ai_confidence=row.ai_confidence,
        title=row.title,
        content=row.content,
        status=PolicyNotificationStatus(row.status),
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        published_by=row.published_by,
        published_at=_utc(row.published_at) if row.published_at else None,
        scopes=scopes,
    )


def _policy_scope_to_entity(row: PolicyScopeRow) -> PolicyScope:
    return PolicyScope(
        id=PolicyScopeId(row.scope_id),
        notification_id=row.notification_id,
        source_document_id=row.source_document_id,
        policy_type=PolicyType(row.policy_type),
        topic=PolicyTopic(row.topic),
        vehicle_type=PolicyVehicleType(row.vehicle_type),
        component=PolicyComponent(row.component),
        battery_chemistry=BatteryChemistry(row.battery_chemistry) if row.battery_chemistry else None,
        ownership_model=BatteryOwnershipModel(row.ownership_model) if row.ownership_model else None,
        usage_type=PolicyUsageType(row.usage_type),
        policy_active_from=row.policy_active_from,
        policy_active_to=row.policy_active_to,
        eligibility_basis=EligibilityBasis(row.eligibility_basis),
        eligibility_from=row.eligibility_from,
        eligibility_to=row.eligibility_to,
        is_current_default=row.is_current_default,
        status=PolicyScopeStatus(row.status),
        supersedes_scope_id=row.supersedes_scope_id,
        affected_models=tuple(row.affected_models),
        resolved_vehicle_ids=tuple(row.resolved_vehicle_ids),
        evidence_quotes=tuple(row.evidence_quotes),
        created_by=row.created_by,
        approved_by=row.approved_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        approved_at=_utc(row.approved_at) if row.approved_at else None,
    )


def _policy_scope_values(scope: PolicyScope) -> dict:
    now = datetime.now(UTC)
    return {
        "scope_id": scope.id.value,
        "notification_id": scope.notification_id,
        "source_document_id": scope.source_document_id,
        "policy_type": scope.policy_type.value,
        "topic": scope.topic.value,
        "vehicle_type": scope.vehicle_type.value,
        "component": scope.component.value,
        "battery_chemistry": scope.battery_chemistry.value if scope.battery_chemistry else None,
        "ownership_model": scope.ownership_model.value if scope.ownership_model else None,
        "usage_type": scope.usage_type.value,
        "policy_active_from": scope.policy_active_from,
        "policy_active_to": scope.policy_active_to,
        "eligibility_basis": scope.eligibility_basis.value,
        "eligibility_from": scope.eligibility_from,
        "eligibility_to": scope.eligibility_to,
        "is_current_default": scope.is_current_default,
        "status": scope.status.value,
        "supersedes_scope_id": scope.supersedes_scope_id,
        "affected_models": list(scope.affected_models),
        "resolved_vehicle_ids": list(scope.resolved_vehicle_ids),
        "evidence_quotes": list(scope.evidence_quotes),
        "created_by": scope.created_by,
        "approved_by": scope.approved_by,
        "created_at": _utc(scope.created_at or now),
        "updated_at": _utc(scope.updated_at or now),
        "approved_at": _utc(scope.approved_at) if scope.approved_at else None,
    }


def _policy_notification_values(notification: PolicyNotification) -> dict:
    return {
        "id": notification.id.value,
        "source_document_id": notification.source_document_id.value,
        "policy_type": notification.policy_type.value,
        "topic": notification.topic.value,
        "secondary_topics": [item.value for item in notification.secondary_topics],
        "affected_models": list(notification.affected_models),
        "effective_from": notification.effective_from,
        "effective_to": notification.effective_to,
        "facts": [
            {"label": item.label, "value": item.value, "evidence": item.evidence}
            for item in notification.facts
        ],
        "evidence": [
            {"section": item.section, "quote": item.quote}
            for item in notification.evidence
        ],
        "ai_confidence": notification.ai_confidence,
        "title": notification.title,
        "content": notification.content,
        "status": notification.status.value,
        "created_by": notification.created_by,
        "published_by": notification.published_by,
        "created_at": _utc(notification.created_at),
        "updated_at": _utc(notification.updated_at),
        "published_at": _utc(notification.published_at) if notification.published_at else None,
    }


class SqlAlchemyDocumentRepository:
    """Document metadata access without byte loading or user-table joins."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> Document:
        await self._session.execute(
            insert(DocumentRow).values(
                id=document.id.value,
                title=document.title,
                description=document.description,
                document_type=document.document_type,
                source_url=document.source_url,
                source_authority=document.source_authority.value,
                source_revision=document.source_revision,
                source_published_at=document.source_published_at,
                source_retrieved_at=document.source_retrieved_at,
                source_etag=document.source_etag,
                source_last_modified=document.source_last_modified,
                supersedes_document_id=document.supersedes_document_id,
                original_filename=document.original_filename,
                object_key=document.object_key,
                content_type=document.content_type,
                byte_size=document.byte_size,
                content_hash=document.content_hash,
                approval_status=document.approval_status.value,
                processing_status=document.processing_status.value,
                created_by=document.created_by,
                created_at=_utc(document.created_at),
                updated_by=document.updated_by,
                updated_at=_utc(document.updated_at or document.created_at),
                archived_by=document.archived_by,
                archived_at=_utc(document.archived_at) if document.archived_at else None,
            )
        )
        return document

    async def get(self, document_id: DocumentId) -> Document | None:
        row = await self._session.get(DocumentRow, document_id.value)
        return _to_document(row) if row else None

    async def get_by_source_hash(self, source_url: str, content_hash: str) -> Document | None:
        row = (
            await self._session.execute(
                select(DocumentRow).where(
                    DocumentRow.source_url == source_url,
                    DocumentRow.content_hash == content_hash,
                )
            )
        ).scalar_one_or_none()
        return _to_document(row) if row else None

    async def get_latest_by_source_url(self, source_url: str) -> Document | None:
        row = (
            await self._session.execute(
                select(DocumentRow)
                .where(DocumentRow.source_url == source_url)
                .order_by(DocumentRow.source_retrieved_at.desc().nullslast(), DocumentRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return _to_document(row) if row else None

    async def list(self, query: ListDocumentsQuery) -> tuple[Document, ...]:
        result = await self._session.execute(
            select(DocumentRow)
            .where(DocumentRow.archived_at.is_(None))
            .order_by(DocumentRow.created_at.desc(), DocumentRow.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return tuple(_to_document(row) for row in result.scalars())

    async def archive(self, document_id: DocumentId, actor_id: str, archived_at: datetime) -> Document:
        moment = _utc(archived_at)
        await self._session.execute(
            update(DocumentRow)
            .where(DocumentRow.id == document_id.value, DocumentRow.archived_at.is_(None))
            .values(archived_at=moment, archived_by=actor_id, updated_at=moment, updated_by=actor_id)
        )
        result = await self._session.execute(select(DocumentRow).where(DocumentRow.id == document_id.value))
        return _to_document(result.scalar_one())


class SqlAlchemyVehicleDocumentRepository:
    """Doc/ghi `vehicle_documents`. Vector search thuoc A1-7, khong o day."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, chunk: VehicleDocument) -> VehicleDocument:
        # `vehicles` is Product-owned metadata. ORM flush attempts to sort the
        # two metadata graphs and cannot resolve that cross-module FK, although
        # PostgreSQL has the migrated target table. A Core insert keeps the
        # boundary and leaves referential integrity to PostgreSQL.
        await self._session.execute(
            VehicleDocumentRow.__table__.insert().values(
                **_vehicle_document_to_row_values(chunk)
            )
        )
        return chunk

    async def get(self, document_id: str) -> VehicleDocument | None:
        row = await self._session.get(VehicleDocumentRow, document_id)
        return _vehicle_document_to_entity(row) if row else None

    async def list_for_vehicle(
        self, vehicle_id: str, *, status: VehicleDocumentStatus | None = None
    ) -> tuple[VehicleDocument, ...]:
        stmt = select(VehicleDocumentRow).where(VehicleDocumentRow.vehicle_id == vehicle_id)
        if status is not None:
            stmt = stmt.where(VehicleDocumentRow.status == status.value)
        stmt = stmt.order_by(VehicleDocumentRow.chunk_index)
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(_vehicle_document_to_entity(r) for r in rows)

    async def approve(self, document_id: str, actor_id: str, approved_at: datetime) -> VehicleDocument | None:
        row = await self._session.get(VehicleDocumentRow, document_id)
        if row is None:
            return None
        row.status = VehicleDocumentStatus.ACTIVE.value
        row.approved_by = actor_id
        row.approved_at = approved_at
        row.updated_at = approved_at
        await self._session.flush()
        return _vehicle_document_to_entity(row)

    async def approve_for_source(
        self, source_document_id: str, actor_id: str, approved_at: datetime
    ) -> int:
        """Activate every DRAFT chunk from one reviewed source in the same transaction."""

        moment = _utc(approved_at)
        result = await self._session.execute(
            update(VehicleDocumentRow)
            .where(
                VehicleDocumentRow.source_document_id == source_document_id,
                VehicleDocumentRow.status == VehicleDocumentStatus.DRAFT.value,
            )
            .values(
                status=VehicleDocumentStatus.ACTIVE.value,
                approved_by=actor_id,
                approved_at=moment,
                updated_at=moment,
            )
        )
        return int(result.rowcount or 0)

    async def summary_for_source(self, source_document_id: str) -> PolicyCorpusSummary:
        """Return source readiness and safe catalog identities without vector payloads."""

        status_rows = (
            await self._session.execute(
                select(VehicleDocumentRow.status, func.count(VehicleDocumentRow.document_id))
                .where(VehicleDocumentRow.source_document_id == source_document_id)
                .group_by(VehicleDocumentRow.status)
            )
        ).all()
        counts = {str(status): int(count) for status, count in status_rows}
        chunk_count = sum(counts.values())
        if counts.get(VehicleDocumentStatus.ACTIVE.value, 0) > 0:
            state = PolicyCorpusState.ACTIVE
        elif counts.get(VehicleDocumentStatus.DRAFT.value, 0) > 0:
            state = PolicyCorpusState.DRAFT
        else:
            state = PolicyCorpusState.NOT_BUILT

        vehicle_rows = (
            await self._session.execute(
                select(
                    distinct(VehicleRow.vehicle_id),
                    VehicleRow.slug,
                    VehicleRow.model_name,
                    VehicleRow.variant_name,
                )
                .join(
                    VehicleDocumentRow,
                    VehicleDocumentRow.vehicle_id == VehicleRow.vehicle_id,
                )
                .where(VehicleDocumentRow.source_document_id == source_document_id)
                .order_by(VehicleRow.slug)
            )
        ).all()
        vehicles = tuple(
            ResolvedPolicyVehicle(
                vehicle_id=str(vehicle_id),
                slug=slug,
                display_name=" ".join(
                    part for part in (model_name, variant_name) if part
                ),
            )
            for vehicle_id, slug, model_name, variant_name in vehicle_rows
        )
        validation_errors: list[str] = []
        chunk_rows = (
            await self._session.execute(
                select(
                    VehicleDocumentRow.vehicle_id,
                    VehicleDocumentRow.policy_scope_id,
                    VehicleDocumentRow.source_url,
                    VehicleDocumentRow.embedding,
                    VehicleDocumentRow.embedding_model,
                    VehicleDocumentRow.embedding_version,
                ).where(VehicleDocumentRow.source_document_id == source_document_id)
            )
        ).all()
        for vehicle_id, scope_id, source_url, embedding, model, version in chunk_rows:
            if vehicle_id is None:
                validation_errors.append("Evidence chưa gắn chính xác mẫu xe.")
            if scope_id is None:
                validation_errors.append("Evidence chưa gắn phạm vi chính sách đã review.")
            if not source_url:
                validation_errors.append("Evidence chưa có URL nguồn chính thức.")
            if embedding is None or len(embedding) != 1024 or not model or not version:
                validation_errors.append("Embedding policy chưa sẵn sàng hoặc sai phiên bản.")
        return PolicyCorpusSummary(
            state,
            chunk_count,
            vehicles,
            tuple(dict.fromkeys(validation_errors)),
        )


class SqlAlchemyPolicyNotificationRepository:
    """Persist one analysis/draft/publication aggregate per source document."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, notification_id: PolicyNotificationId) -> PolicyNotification | None:
        row = await self._session.get(PolicyNotificationRow, notification_id.value)
        if row is None:
            return None
        return _policy_notification_to_entity(row, await self._scopes_for(row.id))

    async def get_by_source(self, source_document_id: DocumentId) -> PolicyNotification | None:
        result = await self._session.execute(
            select(PolicyNotificationRow).where(
                PolicyNotificationRow.source_document_id == source_document_id.value
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _policy_notification_to_entity(row, await self._scopes_for(row.id))

    async def add(self, notification: PolicyNotification) -> PolicyNotification:
        self._session.add(PolicyNotificationRow(**_policy_notification_values(notification)))
        for scope in notification.scopes:
            self._session.add(PolicyScopeRow(**_policy_scope_values(scope)))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise PolicyNotificationConflictError("document already has an analysis") from error
        return notification

    async def save(self, notification: PolicyNotification) -> PolicyNotification:
        row = await self._session.get(PolicyNotificationRow, notification.id.value)
        if row is None:
            raise LookupError(notification.id.value)
        values = _policy_notification_values(notification)
        for key, value in values.items():
            if key != "id":
                setattr(row, key, value)
        for scope in notification.scopes:
            scope_row = await self._session.get(PolicyScopeRow, scope.id.value)
            if scope_row is None:
                raise PolicyNotificationConflictError("policy scope does not exist")
            scope_values = _policy_scope_values(scope)
            for key, value in scope_values.items():
                if key != "scope_id":
                    setattr(scope_row, key, value)
        await self._session.flush()
        return notification

    async def list_published(self, page: int, page_size: int) -> tuple[PolicyNotification, ...]:
        result = await self._session.execute(
            select(PolicyNotificationRow)
            .where(PolicyNotificationRow.status == PolicyNotificationStatus.PUBLISHED.value)
            .order_by(PolicyNotificationRow.published_at.desc(), PolicyNotificationRow.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        notifications: list[PolicyNotification] = []
        for row in result.scalars():
            notifications.append(
                _policy_notification_to_entity(row, await self._scopes_for(row.id))
            )
        return tuple(notifications)

    async def activate_scopes_for_source(
        self,
        source_document_id: str,
        actor_id: str,
        approved_at: datetime,
        resolution: PolicyConflictResolution | None = None,
    ) -> int:
        """Resolve vehicle IDs from built chunks and activate scopes atomically."""
        rows = (
            await self._session.execute(
                select(PolicyScopeRow).where(
                    PolicyScopeRow.source_document_id == source_document_id,
                    PolicyScopeRow.status == PolicyScopeStatus.DRAFT.value,
                )
            )
        ).scalars().all()
        activated = 0
        for row in rows:
            vehicle_ids = tuple(
                str(value)
                for value in (
                    await self._session.execute(
                        select(distinct(VehicleDocumentRow.vehicle_id)).where(
                            VehicleDocumentRow.policy_scope_id == row.scope_id,
                            VehicleDocumentRow.vehicle_id.is_not(None),
                        )
                    )
                ).scalars()
                if value is not None
            )
            candidate = _policy_scope_to_entity(row).with_resolved_vehicles(vehicle_ids)
            active_rows = (
                await self._session.execute(
                    select(PolicyScopeRow).where(
                        PolicyScopeRow.status == PolicyScopeStatus.ACTIVE.value,
                        PolicyScopeRow.source_document_id != source_document_id,
                        PolicyScopeRow.policy_type == row.policy_type,
                        PolicyScopeRow.topic == row.topic,
                        PolicyScopeRow.vehicle_type == row.vehicle_type,
                        PolicyScopeRow.component == row.component,
                        PolicyScopeRow.battery_chemistry.is_not_distinct_from(row.battery_chemistry),
                        PolicyScopeRow.ownership_model.is_not_distinct_from(row.ownership_model),
                        PolicyScopeRow.usage_type == row.usage_type,
                    ).with_for_update()
                )
            ).scalars()
            superseded_scope_ids: list[str] = []
            for active_row in active_rows:
                active_scope = _policy_scope_to_entity(active_row)
                same_vehicles = bool(
                    set(candidate.resolved_vehicle_ids) & set(active_scope.resolved_vehicle_ids)
                )
                if not same_vehicles:
                    continue
                overlap = candidate.cohort_period_overlaps(active_scope)
                default_conflict = candidate.is_current_default and active_scope.is_current_default
                if not overlap and not default_conflict:
                    continue
                if (
                    resolution is PolicyConflictResolution.SUPERSEDE_DEFAULT
                    and candidate.is_current_default
                ):
                    active_row.is_current_default = False
                    active_row.updated_at = approved_at
                    superseded_scope_ids.append(active_scope.id.value)
                    if (
                        overlap
                        and candidate.eligibility_from is not None
                        and active_scope.eligibility_basis is candidate.eligibility_basis
                    ):
                        if (
                            active_scope.eligibility_from is not None
                            and candidate.eligibility_from <= active_scope.eligibility_from
                        ):
                            raise PolicyNotificationConflictError(
                                "the replacement start date must follow the active cohort start"
                            )
                        active_row.eligibility_to = candidate.eligibility_from - timedelta(days=1)
                    continue
                if (
                    resolution is PolicyConflictResolution.COEXIST_BY_COHORT
                    and not overlap
                    and not default_conflict
                ):
                    continue
                if resolution is PolicyConflictResolution.CANCEL or resolution is None:
                    raise PolicyNotificationConflictError(
                        "active policy scope overlaps the reviewed customer cohort"
                    )
                raise PolicyNotificationConflictError(
                    "coexistence requires disjoint customer cohorts"
                )
            if len(superseded_scope_ids) > 1:
                raise PolicyNotificationConflictError(
                    "replacement matches multiple active scopes; repair the revision chain first"
                )
            if superseded_scope_ids:
                candidate = replace(candidate, supersedes_scope_id=superseded_scope_ids[0])
            active = candidate.activate(actor_id, approved_at)
            values = _policy_scope_values(active)
            for key, value in values.items():
                if key != "scope_id":
                    setattr(row, key, value)
            activated += 1
        await self._session.flush()
        return activated

    async def _scopes_for(self, notification_id: str) -> tuple[PolicyScope, ...]:
        rows = (
            await self._session.execute(
                select(PolicyScopeRow)
                .where(PolicyScopeRow.notification_id == notification_id)
                .order_by(PolicyScopeRow.created_at, PolicyScopeRow.scope_id)
            )
        ).scalars()
        return tuple(_policy_scope_to_entity(row) for row in rows)

    async def set_current_default(
        self,
        scope_id: str,
        actor_id: str,
        changed_at: datetime,
    ) -> PolicyScope:
        """Atomically switch only the matching applicability/vehicle family default."""
        target = await self._session.get(PolicyScopeRow, scope_id, with_for_update=True)
        if target is None or target.status != PolicyScopeStatus.ACTIVE.value:
            raise PolicyNotificationConflictError("default target must be an active policy scope")
        target_vehicle_ids = set(target.resolved_vehicle_ids)
        if not target_vehicle_ids:
            raise PolicyNotificationConflictError("default target has no resolved vehicles")
        current_rows = (
            await self._session.execute(
                select(PolicyScopeRow)
                .where(
                    PolicyScopeRow.status == PolicyScopeStatus.ACTIVE.value,
                    PolicyScopeRow.is_current_default.is_(True),
                    PolicyScopeRow.policy_type == target.policy_type,
                    PolicyScopeRow.topic == target.topic,
                    PolicyScopeRow.vehicle_type == target.vehicle_type,
                    PolicyScopeRow.component == target.component,
                    PolicyScopeRow.battery_chemistry.is_not_distinct_from(target.battery_chemistry),
                    PolicyScopeRow.ownership_model.is_not_distinct_from(target.ownership_model),
                    PolicyScopeRow.usage_type == target.usage_type,
                )
                .with_for_update()
            )
        ).scalars()
        moment = _utc(changed_at)
        for row in current_rows:
            if row.scope_id != scope_id and target_vehicle_ids & set(row.resolved_vehicle_ids):
                row.is_current_default = False
                row.updated_at = moment
        target.is_current_default = True
        target.updated_at = moment
        target.approved_by = actor_id
        await self._session.flush()
        return _policy_scope_to_entity(target)


@dataclass(frozen=True, slots=True)
class DocumentRepositories:
    """Repository set scoped to one transaction."""

    documents: SqlAlchemyDocumentRepository
    vehicle_documents: SqlAlchemyVehicleDocumentRepository
    policy_notifications: SqlAlchemyPolicyNotificationRepository


class DocumentUnitOfWork:
    """Commits on normal exit and rolls back all Document metadata changes on error."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[DocumentRepositories]:
        async with self._session_factory() as session, session.begin():
            yield DocumentRepositories(
                documents=SqlAlchemyDocumentRepository(session),
                vehicle_documents=SqlAlchemyVehicleDocumentRepository(session),
                policy_notifications=SqlAlchemyPolicyNotificationRepository(session),
            )
