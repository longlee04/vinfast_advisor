"""Immutable structured-data snapshot capture for A5-2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.agents.contracts import CandidateInput, EvidenceInput, FeatureAssertion
from src.agents.domain.values import RunState
from src.agents.ports import ClockPort, UnitOfWorkPort

SNAPSHOT_SCHEMA_VERSION: Final[Literal["agent_snapshot_v1"]] = "agent_snapshot_v1"
QUOTE_FACT_CODE: Final[str] = "DOC_EXCERPT"
# Assertion mô tả không gắn với tính năng nào; chỉ mang đoạn trích cho diễn giải.
QUOTE_ONLY_FEATURE_CODE: Final[str] = "UNKNOWN_FEATURE"


class SnapshotFact(BaseModel):
    """One immutable structured value and its source record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_code: str = Field(min_length=1, max_length=100)
    value_text: str
    source_table: str = Field(min_length=1, max_length=100)
    source_id: UUID | None = None


class SnapshotCandidate(BaseModel):
    """All structured facts captured for one candidate vehicle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vehicle_id: UUID
    facts: tuple[SnapshotFact, ...]
    model_name: str = ""

    @model_validator(mode="after")
    def facts_have_unique_codes(self) -> SnapshotCandidate:
        """Reject ambiguous snapshots containing two values for one fact."""

        codes = [fact.fact_code for fact in self.facts]
        if len(codes) != len(set(codes)):
            raise ValueError("snapshot candidate fact_code values must be unique")
        return self


class SnapshotFeatureAssertion(BaseModel):
    """Frozen Lớp-2 assertion included in the run snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vehicle_id: UUID
    feature_code: str = Field(min_length=1, max_length=100)
    status: Literal["YES", "NO", "UNKNOWN"]
    source: Literal["FLAG", "DOCUMENT"]
    evidence_ref: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    excerpt: str | None = None


class RunSnapshotEnvelope(BaseModel):
    """Versioned JSON payload persisted in ``run_snapshots``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["agent_snapshot_v1"] = SNAPSHOT_SCHEMA_VERSION
    captured_at: datetime
    candidates: tuple[SnapshotCandidate, ...]
    assertions: tuple[SnapshotFeatureAssertion, ...]


class CatalogSnapshotSource(Protocol):
    """Read effective catalog facts for the requested candidates at one time."""

    async def load(self, *, candidate_ids: tuple[UUID, ...], at: datetime) -> Sequence[SnapshotCandidate]: ...


def parse_snapshot(payload: Mapping[str, object]) -> RunSnapshotEnvelope:
    """Validate persisted JSON before downstream scoring, TCO or synthesis reads it."""

    return RunSnapshotEnvelope.model_validate(payload)


class DefaultSnapshottingService:
    """Capture catalog facts and assertions, then atomically mark a run ready."""

    def __init__(
        self,
        *,
        source: CatalogSnapshotSource,
        unit_of_work: UnitOfWorkPort,
        clock: ClockPort,
    ) -> None:
        self._source = source
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def snapshot(
        self,
        *,
        run_id: UUID,
        candidate_ids: Sequence[UUID],
        assertions: Sequence[FeatureAssertion],
    ) -> None:
        """Persist a detached copy; never retain references to mutable catalog data."""

        ordered_ids = tuple(candidate_ids)
        _validate_candidate_ids(ordered_ids)
        captured_at = self._clock.now()
        loaded = tuple(await self._source.load(candidate_ids=ordered_ids, at=captured_at))
        candidates = _ordered_candidates(ordered_ids, loaded)
        frozen_assertions = _freeze_assertions(assertions, set(ordered_ids))
        envelope = RunSnapshotEnvelope(
            captured_at=captured_at,
            candidates=candidates,
            assertions=frozen_assertions,
        )
        payload = envelope.model_dump(mode="json")
        async with self._unit_of_work.transaction() as transaction:
            await transaction.runs.save_snapshot(run_id, payload)
            await transaction.runs.save_evidence(
                run_id,
                (*_evidence_from(candidates), *quote_evidence_from(frozen_assertions)),
            )
            await transaction.runs.save_candidates(run_id, _candidates_from(candidates, frozen_assertions))
            await transaction.runs.set_state(run_id, RunState.SNAPSHOT_READY.value)


def _evidence_from(candidates: tuple[SnapshotCandidate, ...]) -> tuple[EvidenceInput, ...]:
    """Trải phẳng fact của mọi candidate thành evidence để guardrail tra cứu."""

    return tuple(
        EvidenceInput(
            fact_code=fact.fact_code,
            value_text=fact.value_text,
            source_table=fact.source_table,
            source_id=fact.source_id,
        )
        for candidate in candidates
        for fact in candidate.facts
    )


def quote_evidence_from(
    assertions: Sequence[FeatureAssertion | SnapshotFeatureAssertion],
) -> tuple[EvidenceInput, ...]:
    """Biến đoạn trích tài liệu thành evidence để guardrail đối chiếu nguyên văn."""

    return tuple(
        EvidenceInput(
            fact_code=QUOTE_FACT_CODE,
            value_text=assertion.excerpt,
            source_table="vehicle_documents",
            source_id=_document_id(assertion.evidence_ref),
        )
        for assertion in assertions
        if assertion.source == "DOCUMENT" and assertion.excerpt
    )


def _document_id(evidence_ref: str) -> UUID | None:
    """Tách document ID khỏi evidence reference của vehicle document."""

    source_table, separator, raw_identifier = evidence_ref.partition(":")
    if source_table != "vehicle_documents" or not separator:
        return None
    try:
        return UUID(raw_identifier)
    except ValueError:
        return None


def _candidates_from(
    candidates: tuple[SnapshotCandidate, ...],
    assertions: tuple[SnapshotFeatureAssertion, ...],
) -> tuple[CandidateInput, ...]:
    """Ánh xạ hai lớp thi công về ba tầng tên PRD.

    Không có assertion nào thì xe dừng ở Tầng 1. Có assertion từ flags là Tầng 2.
    Chỉ khi nhánh 2e phải đọc tài liệu (`source="DOCUMENT"`) mới là Tầng 3 — đó
    cũng đúng chỗ tốn chi phí embedding, nên ghi lại có giá trị vận hành.

    Đoạn mô tả (`UNKNOWN_FEATURE`) nay được truy hồi cho mọi lượt, nên nếu tính nó
    là Tầng 3 thì mọi xe đều Tầng 3 và con số mất hết ý nghĩa. Tầng 3 chỉ dành cho
    trường hợp tài liệu được dùng để kết luận một tính năng cụ thể.
    """

    reached: dict[UUID, str] = {}
    for assertion in assertions:
        current = reached.get(assertion.vehicle_id)
        resolved_by_document = assertion.source == "DOCUMENT" and assertion.feature_code != QUOTE_ONLY_FEATURE_CODE
        if resolved_by_document or current == "L3":
            reached[assertion.vehicle_id] = "L3"
        else:
            reached[assertion.vehicle_id] = "L2"
    return tuple(
        CandidateInput(
            vehicle_id=candidate.vehicle_id,
            layer_reached=reached.get(candidate.vehicle_id, "L1"),
        )
        for candidate in candidates
    )


def _validate_candidate_ids(candidate_ids: tuple[UUID, ...]) -> None:
    if not candidate_ids:
        raise ValueError("snapshot requires at least one candidate")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("snapshot candidate_ids must be unique")


def _ordered_candidates(
    candidate_ids: tuple[UUID, ...], loaded: tuple[SnapshotCandidate, ...]
) -> tuple[SnapshotCandidate, ...]:
    loaded_by_id = {candidate.vehicle_id: candidate for candidate in loaded}
    if len(loaded_by_id) != len(loaded) or set(loaded_by_id) != set(candidate_ids):
        raise ValueError("catalog snapshot candidate mismatch")
    return tuple(
        SnapshotCandidate(
            vehicle_id=vehicle_id,
            model_name=loaded_by_id[vehicle_id].model_name,
            facts=tuple(sorted(loaded_by_id[vehicle_id].facts, key=lambda fact: fact.fact_code)),
        )
        for vehicle_id in candidate_ids
    )


def _freeze_assertions(
    assertions: Sequence[FeatureAssertion], candidate_ids: set[UUID]
) -> tuple[SnapshotFeatureAssertion, ...]:
    outside = {assertion.vehicle_id for assertion in assertions} - candidate_ids
    if outside:
        raise ValueError("feature assertion references vehicle outside candidate set")
    frozen = (
        SnapshotFeatureAssertion(
            vehicle_id=assertion.vehicle_id,
            feature_code=assertion.feature_code,
            status=assertion.status,
            source=assertion.source,
            evidence_ref=assertion.evidence_ref,
            confidence=assertion.confidence,
            excerpt=assertion.excerpt,
        )
        for assertion in assertions
    )
    return tuple(
        sorted(
            frozen,
            key=lambda assertion: (
                str(assertion.vehicle_id),
                assertion.feature_code,
                assertion.source,
                assertion.evidence_ref,
            ),
        )
    )
