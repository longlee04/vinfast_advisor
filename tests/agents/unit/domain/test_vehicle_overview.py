"""Contract tests for vehicle overview query classification and evidence."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.domain.vehicle_overview import (
    EvidenceItem,
    PriceVariant,
    VehicleAttribute,
    VehicleOverview,
    classify_query_attribute,
)


def test_detail_keyword_wins_over_price_keyword() -> None:
    """A full-overview request must not fall through to the price-only path."""

    assert classify_query_attribute("cho em xem chi tiết giá vf7") is VehicleAttribute.OVERVIEW


def test_plain_price_question_stays_price() -> None:
    """Removing an overview keyword must preserve the existing price route."""

    assert classify_query_attribute("vf9 giá bao nhiêu") is VehicleAttribute.PRICE


@pytest.mark.parametrize(
    "message",
    [
        "tư vấn xe vf5",
        "thông tin chi tiết xe vf7",
        "đầy đủ",
        "tất cả thông tin",
        "toàn bộ thông tin",
        "thông tin về xe",
        "thông tin xe",
    ],
)
def test_overview_phrases_select_overview(message: str) -> None:
    """Each supported full-information phrase must select the overview route."""

    assert classify_query_attribute(message) is VehicleAttribute.OVERVIEW


def test_evidence_rejects_empty_content_and_identifier() -> None:
    """Evidence without text or an identifier cannot be rendered as a source."""

    with pytest.raises(ValidationError):
        EvidenceItem(content="", evidence_id="")


@pytest.mark.parametrize(
    ("content", "evidence_id"),
    [("   ", "evidence-1"), ("Nội dung có nguồn", "\t\n")],
)
def test_evidence_rejects_whitespace_only_content_or_identifier(content: str, evidence_id: str) -> None:
    """Whitespace-only evidence values cannot become source-less RAG bullets."""

    with pytest.raises(ValidationError):
        EvidenceItem(content=content, evidence_id=evidence_id)


def test_overview_exposes_the_approved_price_and_safety_field_names() -> None:
    """The builder must receive the approved public field names, not legacy names."""

    overview = VehicleOverview(
        vehicle_name="VF 7",
        price_variants=[
            PriceVariant(
                vehicle_id="11111111-1111-1111-1111-111111111111",
                variant_name="Eco",
                amount_vnd=799_000_000,
                price_type="STARTING_PRICE",
                region_code="VN",
            )
        ],
        safety_systems=[EvidenceItem(content="Hỗ trợ phanh", evidence_id="22222222-2222-2222-2222-222222222222")],
    )

    assert overview.price_variants[0].variant_name == "Eco"
    assert overview.safety_systems[0].content == "Hỗ trợ phanh"
    assert not hasattr(overview, "prices")
    assert not hasattr(overview, "safety")


@pytest.mark.parametrize("legacy_field", ["prices", "safety"])
def test_overview_rejects_legacy_field_names(legacy_field: str) -> None:
    """Rejected field names must fail instead of silently dropping overview data."""

    with pytest.raises(ValidationError):
        VehicleOverview(vehicle_name="VF 7", **{legacy_field: []})
