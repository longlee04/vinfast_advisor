"""Policy analysis must create reviewable RAG chunks without auto-publishing them."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.document.application.errors import PolicyCorpusEmptyError, PolicyEmbeddingUnavailableError
from src.document.application.policy_corpus import (
    DefaultPolicyCorpusBuilder,
    PolicyCorpusState,
    PolicyCorpusSummary,
    ResolvedPolicyVehicle,
)
from src.document.domain.entities import Document
from src.document.domain.policy_notifications import (
    PolicyEvidence,
    PolicyFact,
    PolicyNotification,
    PolicyTopic,
    PolicyType,
)
from src.document.domain.values import (
    ApprovalStatus,
    DocumentId,
    ProcessingStatus,
    VehicleDocumentStatus,
)
from src.document.presentation.schemas import PolicyNotificationResponse


class Resolver:
    async def resolve_vehicle_ids(
        self, affected_models: tuple[str, ...], **kwargs: object
    ) -> tuple[str, ...]:
        del kwargs
        assert affected_models == ("VF7",)
        return (
            "00000000-0000-0000-0000-000000000701",
            "00000000-0000-0000-0000-000000000702",
        )


class Embedding:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        return [[0.25] * 1024 for _ in texts]


class InvalidEmbedding:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.25] * 1536 for _ in texts]


def _document() -> Document:
    return Document(
        id=DocumentId("00000000-0000-0000-0000-000000000001"),
        title="Sổ bảo hành VF7",
        content_hash="a" * 64,
        created_by="admin-1",
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
        approval_status=ApprovalStatus.DRAFT,
        processing_status=ProcessingStatus.COMPLETED,
        source_url="https://vinfastauto.com/vn_vi/thong-tin-bao-hanh",
        object_key="documents/warranty.pdf",
    )


def _notification() -> PolicyNotification:
    return PolicyNotification.create_draft(
        source_document_id=_document().id,
        policy_type=PolicyType.WARRANTY_POLICY,
        topic=PolicyTopic.BATTERY_WARRANTY,
        secondary_topics=(PolicyTopic.VEHICLE_WARRANTY,),
        affected_models=("VF7",),
        effective_from=date(2026, 9, 1),
        effective_to=date(2027, 8, 31),
        facts=(
            PolicyFact(
                "Thời hạn bảo hành pin",
                "8 năm hoặc 160.000 km",
                "Pin VF7 được bảo hành 8 năm hoặc 160.000 km.",
            ),
        ),
        evidence=(
            PolicyEvidence("Pin VF7 được bảo hành 8 năm hoặc 160.000 km.", "3.2"),
        ),
        ai_confidence=0.98,
        title="Bảo hành pin VF7",
        content="Bản thông báo dành cho khách hàng không phải evidence RAG.",
        actor_id="admin-1",
    )


@pytest.mark.asyncio
async def test_builder_creates_deduplicated_drafts_for_exact_resolved_vehicles() -> None:
    embedding = Embedding()
    builder = DefaultPolicyCorpusBuilder(
        resolver=Resolver(),
        embedding=embedding,
        now=lambda: datetime(2026, 8, 30, 12, tzinfo=UTC),
    )

    chunks = await builder.build_drafts(
        _document(),
        _notification(),
        "Mở đầu\nPin VF7 được bảo hành 8 năm hoặc 160.000 km.\nKết thúc",
    )

    assert embedding.texts == ["Pin VF7 được bảo hành 8 năm hoặc 160.000 km."]
    assert len(chunks) == 2
    assert {chunk.vehicle_id for chunk in chunks} == {
        "00000000-0000-0000-0000-000000000701",
        "00000000-0000-0000-0000-000000000702",
    }
    assert all(chunk.status is VehicleDocumentStatus.DRAFT for chunk in chunks)
    assert all(chunk.approved_by is None and chunk.approved_at is None for chunk in chunks)
    assert all(chunk.document_type == "WARRANTY_POLICY" for chunk in chunks)
    assert all(chunk.section_title == "BATTERY_WARRANTY:3.2" for chunk in chunks)
    assert all(chunk.source_document_id == _document().id.value for chunk in chunks)
    assert all(chunk.source_content_hash == "a" * 64 for chunk in chunks)
    assert all(chunk.source_revision == ("a" * 40) for chunk in chunks)
    assert all(chunk.valid_from == datetime(2026, 9, 1, tzinfo=UTC) for chunk in chunks)
    assert all(chunk.valid_to == datetime(2027, 9, 1, tzinfo=UTC) for chunk in chunks)
    assert all(chunk.source_url == _document().source_url for chunk in chunks)
    assert all(len(chunk.embedding or []) == 1024 for chunk in chunks)


@pytest.mark.asyncio
async def test_builder_rejects_a_policy_without_literal_source_evidence() -> None:
    notification = PolicyNotification.create_draft(
        source_document_id=_document().id,
        policy_type=PolicyType.WARRANTY_POLICY,
        topic=PolicyTopic.VEHICLE_WARRANTY,
        secondary_topics=(),
        affected_models=("VF7",),
        effective_from=None,
        effective_to=None,
        facts=(),
        evidence=(),
        ai_confidence=0.9,
        title="Bảo hành VF7",
        content="Chỉ có nội dung thông báo do AI soạn.",
        actor_id="admin-1",
    )

    with pytest.raises(PolicyCorpusEmptyError):
        await DefaultPolicyCorpusBuilder(Resolver(), Embedding()).build_drafts(
            _document(), notification, "Nguồn không có evidence."
        )


@pytest.mark.asyncio
async def test_builder_rejects_fallback_vectors_instead_of_persisting_them() -> None:
    with pytest.raises(PolicyEmbeddingUnavailableError):
        await DefaultPolicyCorpusBuilder(Resolver(), InvalidEmbedding()).build_drafts(
            _document(),
            _notification(),
            "Pin VF7 được bảo hành 8 năm hoặc 160.000 km.",
        )


@pytest.mark.asyncio
async def test_builder_rejects_paraphrased_evidence_not_present_in_source() -> None:
    with pytest.raises(PolicyCorpusEmptyError):
        await DefaultPolicyCorpusBuilder(Resolver(), Embedding()).build_drafts(
            _document(),
            _notification(),
            "Nguồn chỉ nói thời hạn pin theo sổ bảo hành, không có câu trích dẫn này.",
        )


def test_admin_response_exposes_readiness_without_embedding_payload() -> None:
    summary = PolicyCorpusSummary(
        state=PolicyCorpusState.DRAFT,
        chunk_count=2,
        resolved_vehicles=(
            ResolvedPolicyVehicle(
                vehicle_id="00000000-0000-0000-0000-000000000701",
                slug="vinfast-vf-7-all-new",
                display_name="VF 7 All New",
            ),
        ),
    )

    response = PolicyNotificationResponse.from_notification(_notification(), summary)
    payload = response.model_dump(mode="json")

    assert payload["corpus_state"] == "DRAFT"
    assert payload["corpus_chunk_count"] == 2
    assert payload["resolved_vehicles"][0]["slug"] == "vinfast-vf-7-all-new"
    assert "embedding" not in payload
