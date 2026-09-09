"""Build reviewable vehicle-policy RAG chunks from controlled source evidence."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from src.document.application.errors import PolicyCorpusEmptyError, PolicyEmbeddingUnavailableError
from src.document.domain.entities import Document, VehicleDocument
from src.document.domain.policy_notifications import PolicyNotification
from src.document.domain.policy_scopes import BatteryChemistry, PolicyVehicleType
from src.document.domain.values import VehicleDocumentStatus

VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS = 1024
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_EMBEDDING_VERSION = "v1"


class PolicyEmbeddingPort(Protocol):
    """Embedding capability used after policy evidence passed validation."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class PolicyVehicleResolver(Protocol):
    """Resolve reviewed model names/slugs to exact active catalog identifiers."""

    async def resolve_vehicle_ids(
        self,
        affected_models: tuple[str, ...],
        *,
        vehicle_type: PolicyVehicleType | None = None,
        battery_chemistry: BatteryChemistry | None = None,
    ) -> tuple[str, ...]: ...


class PolicyCorpusBuilder(Protocol):
    """Create DRAFT chunks; only explicit Admin publication may activate them."""

    async def build_drafts(
        self,
        document: Document,
        notification: PolicyNotification,
        source_text: str,
    ) -> tuple[VehicleDocument, ...]: ...


class PolicyCorpusState(StrEnum):
    """Admin-visible lifecycle derived from persisted source chunks."""

    NOT_BUILT = "NOT_BUILT"
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"


@dataclass(frozen=True, slots=True)
class ResolvedPolicyVehicle:
    """Safe catalog identity shown to the Admin reviewer."""

    vehicle_id: str
    slug: str
    display_name: str


@dataclass(frozen=True, slots=True)
class PolicyCorpusSummary:
    """Review readiness for chunks derived from one source document."""

    state: PolicyCorpusState
    chunk_count: int
    resolved_vehicles: tuple[ResolvedPolicyVehicle, ...] = ()
    validation_errors: tuple[str, ...] = ()


class PolicyCorpusSummaryReader(Protocol):
    """Read source-level corpus readiness without exposing embeddings."""

    async def summary_for_source(self, source_document_id: str) -> PolicyCorpusSummary: ...


@dataclass(frozen=True, slots=True)
class _EvidenceChunk:
    content: str
    section: str


def _now_utc() -> datetime:
    return datetime.now(UTC)


class DefaultPolicyCorpusBuilder:
    """Convert literal, deduplicated source evidence into per-vehicle DRAFT rows."""

    def __init__(
        self,
        resolver: PolicyVehicleResolver,
        embedding: PolicyEmbeddingPort,
        *,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        embedding_version: str = DEFAULT_EMBEDDING_VERSION,
        now: Callable[[], datetime] = _now_utc,
    ) -> None:
        self._resolver = resolver
        self._embedding = embedding
        self._embedding_model = embedding_model
        self._embedding_version = embedding_version
        self._now = now

    async def build_drafts(
        self,
        document: Document,
        notification: PolicyNotification,
        source_text: str,
    ) -> tuple[VehicleDocument, ...]:
        """Build one chunk per unique evidence/vehicle pair without activating it."""

        if not document.source_url:
            raise PolicyCorpusEmptyError()
        now = self._now().astimezone(UTC)
        revision = document.content_hash[:40]
        rows: list[VehicleDocument] = []
        scope_inputs = [
            (
                scope.id.value,
                scope.topic.value,
                scope.policy_type.value.upper(),
                scope.affected_models,
                scope.vehicle_type,
                scope.battery_chemistry,
                tuple(_EvidenceChunk(quote, "SOURCE") for quote in scope.evidence_quotes),
                scope.policy_active_from,
                scope.policy_active_to,
            )
            for scope in notification.scopes
        ] or [
            (
                None,
                notification.topic.value,
                notification.policy_type.value.upper(),
                notification.affected_models,
                None,
                None,
                _literal_evidence(notification, source_text),
                notification.effective_from,
                notification.effective_to,
            )
        ]
        for (
            scope_id,
            topic,
            document_type,
            affected_models,
            vehicle_type,
            battery_chemistry,
            candidates,
            active_from,
            active_to,
        ) in scope_inputs:
            evidence = _validate_literal_candidates(candidates, source_text)
            if not evidence:
                raise PolicyCorpusEmptyError()
            vehicle_ids = await self._resolver.resolve_vehicle_ids(
                affected_models,
                vehicle_type=vehicle_type,
                battery_chemistry=battery_chemistry,
            )
            if not vehicle_ids:
                raise PolicyCorpusEmptyError()
            vectors = await self._embedding.embed([item.content for item in evidence])
            if len(vectors) != len(evidence) or any(
                len(vector) != VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS for vector in vectors
            ):
                raise PolicyEmbeddingUnavailableError()
            valid_from = _start_of_day(active_from)
            valid_to = _exclusive_end(active_to)
            if valid_from is not None and valid_to is not None and valid_to <= valid_from:
                raise ValueError("policy effective period is invalid")
            rows.extend(
                self._rows_for_scope(
                    document=document,
                    notification=notification,
                    scope_id=scope_id,
                    topic=topic,
                    document_type=document_type,
                    evidence=evidence,
                    vectors=vectors,
                    vehicle_ids=vehicle_ids,
                    revision=revision,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    now=now,
                )
            )
        return tuple(rows)

    def _rows_for_scope(
        self,
        *,
        document: Document,
        notification: PolicyNotification,
        scope_id: str | None,
        topic: str,
        document_type: str,
        evidence: tuple[_EvidenceChunk, ...],
        vectors: list[list[float]],
        vehicle_ids: tuple[str, ...],
        revision: str,
        valid_from: datetime | None,
        valid_to: datetime | None,
        now: datetime,
    ) -> list[VehicleDocument]:
        """Create deterministic corpus rows for one reviewed scope."""
        rows: list[VehicleDocument] = []
        for chunk_index, (item, vector) in enumerate(zip(evidence, vectors, strict=True)):
            for vehicle_id in vehicle_ids:
                stable_key = (
                    f"policy:{document.id.value}:{scope_id or 'legacy'}:{vehicle_id}:{topic}:"
                    f"{chunk_index}:{document.content_hash}"
                )
                rows.append(
                    VehicleDocument(
                        document_id=str(uuid5(NAMESPACE_URL, stable_key)),
                        vehicle_id=vehicle_id,
                        policy_scope_id=scope_id,
                        source_document_id=document.id.value,
                        source_content_hash=document.content_hash,
                        source_revision=revision,
                        document_type=document_type,
                        title=document.title[:255],
                        content=item.content,
                        chunk_index=chunk_index,
                        section_title=(
                            f"{topic.upper()}:{item.section}"[:255]
                        ),
                        source_url=document.source_url,
                        embedding_model=self._embedding_model,
                        embedding_version=self._embedding_version,
                        embedding=list(vector),
                        status=VehicleDocumentStatus.DRAFT,
                        valid_from=valid_from,
                        valid_to=valid_to,
                        created_by=notification.created_by,
                        created_at=now,
                        updated_at=now,
                    )
                )
        return rows


def _literal_evidence(
    notification: PolicyNotification,
    source_text: str,
) -> tuple[_EvidenceChunk, ...]:
    """Use source quotes only; never index the customer notification draft as evidence."""

    candidates = [
        _EvidenceChunk(item.quote.strip(), (item.section or "SOURCE").strip())
        for item in notification.evidence
        if item.quote.strip()
    ]
    candidates.extend(
        _EvidenceChunk(item.evidence.strip(), item.label.strip() or "FACT")
        for item in notification.facts
        if item.evidence.strip()
    )
    return _validate_literal_candidates(tuple(candidates), source_text)


def _validate_literal_candidates(
    candidates: tuple[_EvidenceChunk, ...], source_text: str
) -> tuple[_EvidenceChunk, ...]:
    normalized_source = _normalized_whitespace(source_text).casefold()
    if not normalized_source:
        raise PolicyCorpusEmptyError()
    seen: set[str] = set()
    unique: list[_EvidenceChunk] = []
    for item in candidates:
        key = _normalized_whitespace(item.content).casefold()
        if key not in normalized_source:
            raise PolicyCorpusEmptyError()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _normalized_whitespace(value: str) -> str:
    return " ".join(value.split())


def _start_of_day(value: date | None) -> datetime | None:
    return datetime.combine(value, time.min, tzinfo=UTC) if value is not None else None


def _exclusive_end(value: date | None) -> datetime | None:
    return _start_of_day(value + timedelta(days=1)) if value is not None else None
