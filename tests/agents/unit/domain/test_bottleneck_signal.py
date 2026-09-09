"""Pure bottleneck signal domain contracts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    BottleneckDetectionStatus,
    BottleneckSignal,
    BottleneckSignalStatus,
    ConfirmedBottleneckEvidence,
    OpportunitySignal,
    SignalClaimDeniedError,
    SignalInsert,
    SignalVerdict,
)
from src.agents.domain.customer_profile import Bottleneck


def test_low_confidence_detection_disables_automatic_offer_suggestion() -> None:
    # Given
    detection = BottleneckDetected(
        status=BottleneckDetectionStatus.DETECTED,
        label=Bottleneck.PRICE,
        evidence_quote="giá cao",
        confidence=0.59,
    )

    # When / Then
    assert detection.allows_offer_suggestion is False
    assert detection.offer_suggestion_withheld is True


def test_none_detection_keeps_offer_suggestion_despite_default_confidence() -> None:
    # Lượt không có nút thắt mang confidence mặc định 0.0; nó KHÔNG được kéo
    # theo việc chặn gợi ý ưu đãi.
    detection = BottleneckDetected(
        status=BottleneckDetectionStatus.NONE,
        label=Bottleneck.PRICE,
        evidence_quote="binh thuong",
    )

    assert detection.allows_offer_suggestion is True
    assert detection.offer_suggestion_withheld is False


def test_signal_insert_rejects_empty_evidence() -> None:
    # Given / When / Then
    with pytest.raises(ValueError, match="evidence"):
        SignalInsert(
            session_id=uuid4(),
            client_turn_id=uuid4(),
            anchor_client_turn_id=uuid4(),
            label=Bottleneck.PRICE,
            evidence_quote=" ",
            model_name="model",
            prompt_version="v1",
        )


def test_signal_domain_preserves_redacted_evidence_and_typed_state() -> None:
    # Given
    now = datetime(2026, 8, 23, tzinfo=UTC)
    evidence = "token=[REDACTED]"

    # When
    signal = BottleneckSignal(
        signal_id=uuid4(),
        session_id=uuid4(),
        client_turn_id=uuid4(),
        anchor_client_turn_id=uuid4(),
        label=Bottleneck.RANGE,
        evidence_quote=evidence,
        model_name="model",
        prompt_version="v1",
        status=BottleneckSignalStatus.PENDING,
        claimed_by=None,
        claimed_at=None,
        lease_expires_at=None,
        advisor_id=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )

    # Then
    assert signal.evidence_quote == evidence
    assert signal.status is BottleneckSignalStatus.PENDING


def test_opportunity_signal_uses_set_based_labels() -> None:
    # Given / When
    session_id = uuid4()
    now = datetime(2026, 8, 23, tzinfo=UTC)
    evidence = ConfirmedBottleneckEvidence(
        signal_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=3,
        label=Bottleneck.PRICE,
        evidence_quote="giá cao quá",
    )
    opportunity = OpportunitySignal(
        session_id=session_id,
        customer_id="customer-1",
        labels=frozenset({Bottleneck.PRICE, Bottleneck.RANGE}),
        evidence=(evidence,),
        last_active_at=now,
        latest_signal_at=now,
        correct_signal_count=2,
    )

    # Then
    assert opportunity.labels == frozenset({Bottleneck.PRICE, Bottleneck.RANGE})


def test_typed_claim_error_contains_signal_and_advisor() -> None:
    # Given
    signal_id = uuid4()

    # When
    error = SignalClaimDeniedError(signal_id=signal_id, advisor_id="advisor-2")

    # Then
    assert str(signal_id) in str(error)
    assert "advisor-2" in str(error)
    assert SignalVerdict.CORRECT.value == "CORRECT"
