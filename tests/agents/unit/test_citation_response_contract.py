"""Contract test: citation ở biên giới JSON chỉ phơi `index`, không lộ UUID/tên bảng nội bộ."""

from uuid import UUID

from src.agents.api.routes import CitationResponse, RecommendedVehicle, TurnResponse

VEHICLE_ID = UUID("20000000-0000-0000-0000-000000000101")


def test_citation_response_exposes_only_index() -> None:
    assert set(CitationResponse.model_fields) == {"index"}


def test_turn_response_json_has_no_internal_evidence_fields() -> None:
    recommendation = RecommendedVehicle(
        vehicle_id=VEHICLE_ID,
        rank=1,
        display_name="Xe Một",
        pitch="Xe Một đi 399 km [1].",
        citations=[CitationResponse(index=1)],
    )
    payload = TurnResponse(
        answer="Xe Một đi 399 km [1].",
        pending_question=None,
        lookup_facts=[],
        terminal_reason=None,
        recommendations=[recommendation],
    ).model_dump()

    public_citation = payload["recommendations"][0]["citations"][0]
    assert public_citation == {"index": 1}
    assert set(public_citation) == {"index"}
    serialized = str(payload)
    assert str(VEHICLE_ID) not in str(public_citation)
    assert "evidence_id" not in serialized
    assert "source_record" not in serialized
    assert "document_id" not in serialized
