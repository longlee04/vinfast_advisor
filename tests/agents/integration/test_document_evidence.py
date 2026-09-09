"""Doan trich brochure phai duoc luu thanh evidence de guardrail doi chieu."""

from __future__ import annotations

from uuid import uuid4

from src.agents.contracts import FeatureAssertion
from src.agents.services.snapshotting import QUOTE_FACT_CODE, quote_evidence_from


def test_document_assertion_with_excerpt_becomes_evidence() -> None:
    document_id = uuid4()
    assertion = FeatureAssertion(
        vehicle_id=uuid4(),
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="DOCUMENT",
        evidence_ref=f"vehicle_documents:{document_id}",
        confidence=0.8,
        excerpt="Cửa sổ trời toàn cảnh chống tia UV",
    )

    evidence = quote_evidence_from((assertion,))

    assert len(evidence) == 1
    assert evidence[0].fact_code == QUOTE_FACT_CODE
    assert evidence[0].value_text == "Cửa sổ trời toàn cảnh chống tia UV"
    assert evidence[0].source_table == "vehicle_documents"
    assert evidence[0].source_id == document_id


def test_flag_assertion_produces_no_quote_evidence() -> None:
    assertion = FeatureAssertion(
        vehicle_id=uuid4(),
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:x:y",
        confidence=1.0,
    )

    assert quote_evidence_from((assertion,)) == ()
