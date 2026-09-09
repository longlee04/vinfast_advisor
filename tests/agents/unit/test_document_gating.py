"""Nhanh 2e phai chay ca khi khong khop ma feature nao (quyet dinh 2026-08-11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.agents.adapters.feature_retriever as feature_retriever
from src.agents.adapters.feature_retriever import (
    PLACEHOLDER_FEATURE_CODE,
    FeatureRetrievalAdapter,
    documents_needed,
)
from src.agents.contracts import FeatureAssertion


def _assertion(feature_code: str, status: str) -> FeatureAssertion:
    return FeatureAssertion(
        vehicle_id=uuid4(),
        feature_code=feature_code,
        status=status,
        source="FLAG",
        evidence_ref="test",
        confidence=None,
    )


def _placeholder_target(vehicle_id) -> FeatureAssertion:
    return FeatureAssertion(
        vehicle_id=vehicle_id,
        feature_code=PLACEHOLDER_FEATURE_CODE,
        status="UNKNOWN",
        source="FLAG",
        evidence_ref="below_similarity_threshold",
        confidence=None,
    )


def test_unmatched_utterance_still_reads_documents() -> None:
    assertions = [_assertion(PLACEHOLDER_FEATURE_CODE, "UNKNOWN")]

    assert documents_needed(assertions) == assertions


def test_unknown_flag_still_reads_documents() -> None:
    assertions = [_assertion("PANORAMIC_ROOF", "UNKNOWN")]

    assert documents_needed(assertions) == assertions


def test_concluded_flag_does_not_read_documents() -> None:
    assertions = [_assertion("PANORAMIC_ROOF", "YES"), _assertion("FAST_CHARGE", "NO")]

    assert documents_needed(assertions) == []


@pytest.mark.asyncio
async def test_placeholder_document_hit_does_not_reverse_write(monkeypatch) -> None:
    vehicle_id = uuid4()
    document_rows = MagicMock()
    document_rows.all.return_value = [("document-1", str(vehicle_id), "Cửa sổ trời toàn cảnh chống tia UV")]
    session = AsyncMock()
    session.execute.side_effect = [document_rows, document_rows]
    reverse_write = AsyncMock()
    monkeypatch.setattr(feature_retriever, "reverse_write_pending_flag", reverse_write)
    adapter = FeatureRetrievalAdapter(session)

    assertions = await adapter._retrieve_documents_hybrid(
        query_text="unmatched phrasing",
        query_vec=[0.1],
        candidate_ids=[str(vehicle_id)],
        target_assertions=[
            FeatureAssertion(
                vehicle_id=vehicle_id,
                feature_code=PLACEHOLDER_FEATURE_CODE,
                status="UNKNOWN",
                source="FLAG",
                evidence_ref="below_similarity_threshold",
                confidence=None,
            )
        ],
    )

    assert assertions[0].source == "DOCUMENT"
    reverse_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_every_candidate_vehicle_gets_its_own_document(monkeypatch) -> None:
    """Top-1 toàn cục bỏ rơi các xe còn lại; mỗi xe phải nhận tài liệu của chính nó."""

    first_vehicle, second_vehicle = uuid4(), uuid4()
    document_rows = MagicMock()
    document_rows.all.return_value = [
        ("doc-1", str(first_vehicle), "Khoang lái rộng rãi, ghế bọc da nhân tạo."),
        ("doc-2", str(second_vehicle), "Hàng ghế thứ hai ngả được, phù hợp đi xa."),
    ]
    session = AsyncMock()
    session.execute.side_effect = [document_rows, document_rows]
    monkeypatch.setattr(feature_retriever, "reverse_write_pending_flag", AsyncMock())
    adapter = FeatureRetrievalAdapter(session)

    assertions = await adapter._retrieve_documents_hybrid(
        query_text="xe nào ngồi thoải mái",
        query_vec=[0.1],
        candidate_ids=[str(first_vehicle), str(second_vehicle)],
        target_assertions=[
            _placeholder_target(first_vehicle),
            _placeholder_target(second_vehicle),
        ],
    )

    assert {assertion.vehicle_id for assertion in assertions} == {first_vehicle, second_vehicle}
    assert all(assertion.excerpt for assertion in assertions)


@pytest.mark.asyncio
async def test_unrelated_document_does_not_assert_the_feature(monkeypatch) -> None:
    """Đoạn tả ghế ngồi không được dùng để khẳng định xe có eSIM."""

    vehicle_id = uuid4()
    document_rows = MagicMock()
    document_rows.all.return_value = [("doc-1", str(vehicle_id), "Ghế bọc da, chỉnh điện 8 hướng.")]
    feature_rows = MagicMock()
    feature_rows.all.return_value = [("ESIM", "eSIM tích hợp")]
    session = AsyncMock()
    session.execute.side_effect = [document_rows, document_rows, feature_rows]
    reverse_write = AsyncMock()
    monkeypatch.setattr(feature_retriever, "reverse_write_pending_flag", reverse_write)
    adapter = FeatureRetrievalAdapter(session)

    assertions = await adapter._retrieve_documents_hybrid(
        query_text="xe có esim không",
        query_vec=[0.1],
        candidate_ids=[str(vehicle_id)],
        target_assertions=[
            FeatureAssertion(
                vehicle_id=vehicle_id,
                feature_code="ESIM",
                status="UNKNOWN",
                source="FLAG",
                evidence_ref="flag_not_found",
                confidence=None,
            )
        ],
    )

    assert assertions[0].status == "UNKNOWN"
    assert assertions[0].excerpt
    reverse_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_matching_document_still_asserts_the_feature(monkeypatch) -> None:
    """Đoạn nhắc đúng tính năng vẫn kết luận YES và ghi ngược flag chờ duyệt."""

    vehicle_id = uuid4()
    document_rows = MagicMock()
    document_rows.all.return_value = [("doc-1", str(vehicle_id), "Xe hỗ trợ kết nối Bluetooth và Apple CarPlay.")]
    feature_rows = MagicMock()
    feature_rows.all.return_value = [("BLUETOOTH", "Bluetooth")]
    session = AsyncMock()
    session.execute.side_effect = [document_rows, document_rows, feature_rows]
    reverse_write = AsyncMock()
    monkeypatch.setattr(feature_retriever, "reverse_write_pending_flag", reverse_write)
    adapter = FeatureRetrievalAdapter(session)

    assertions = await adapter._retrieve_documents_hybrid(
        query_text="xe có bluetooth không",
        query_vec=[0.1],
        candidate_ids=[str(vehicle_id)],
        target_assertions=[
            FeatureAssertion(
                vehicle_id=vehicle_id,
                feature_code="BLUETOOTH",
                status="UNKNOWN",
                source="FLAG",
                evidence_ref="flag_not_found",
                confidence=None,
            )
        ],
    )

    assert assertions[0].status == "YES"
    reverse_write.assert_awaited_once()
