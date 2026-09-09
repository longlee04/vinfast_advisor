"""Lưới an toàn cho `_candidates_from`: ánh xạ hai lớp thi công về ba tầng PRD."""

from __future__ import annotations

from uuid import UUID

from src.agents.services.snapshotting import (
    SnapshotCandidate,
    SnapshotFeatureAssertion,
    _candidates_from,
)

VEHICLE_ID = UUID("40000000-0000-0000-0000-000000000001")


def test_candidate_without_any_assertion_stays_at_layer_1() -> None:
    candidates = (SnapshotCandidate(vehicle_id=VEHICLE_ID, facts=()),)

    result = _candidates_from(candidates, ())

    assert result[0].layer_reached == "L1"


def test_candidate_with_only_flag_assertion_reaches_layer_2() -> None:
    candidates = (SnapshotCandidate(vehicle_id=VEHICLE_ID, facts=()),)
    assertions = (
        SnapshotFeatureAssertion(
            vehicle_id=VEHICLE_ID,
            feature_code="HOME_CHARGING",
            status="YES",
            source="FLAG",
            evidence_ref="feature_flags:HOME_CHARGING",
        ),
    )

    result = _candidates_from(candidates, assertions)

    assert result[0].layer_reached == "L2"


def test_candidate_with_flag_then_document_reaches_layer_3() -> None:
    candidates = (SnapshotCandidate(vehicle_id=VEHICLE_ID, facts=()),)
    assertions = (
        SnapshotFeatureAssertion(
            vehicle_id=VEHICLE_ID,
            feature_code="HOME_CHARGING",
            status="YES",
            source="FLAG",
            evidence_ref="feature_flags:HOME_CHARGING",
        ),
        SnapshotFeatureAssertion(
            vehicle_id=VEHICLE_ID,
            feature_code="ADAS_LEVEL_2",
            status="YES",
            source="DOCUMENT",
            evidence_ref="doc:spec_sheet#12",
        ),
    )

    result = _candidates_from(candidates, assertions)

    assert result[0].layer_reached == "L3"


def test_candidate_with_document_then_flag_still_reaches_layer_3() -> None:
    """Cùng dữ liệu case trên nhưng đảo thứ tự: kết quả không phụ thuộc thứ tự duyệt."""

    candidates = (SnapshotCandidate(vehicle_id=VEHICLE_ID, facts=()),)
    assertions = (
        SnapshotFeatureAssertion(
            vehicle_id=VEHICLE_ID,
            feature_code="ADAS_LEVEL_2",
            status="YES",
            source="DOCUMENT",
            evidence_ref="doc:spec_sheet#12",
        ),
        SnapshotFeatureAssertion(
            vehicle_id=VEHICLE_ID,
            feature_code="HOME_CHARGING",
            status="YES",
            source="FLAG",
            evidence_ref="feature_flags:HOME_CHARGING",
        ),
    )

    result = _candidates_from(candidates, assertions)

    assert result[0].layer_reached == "L3"
