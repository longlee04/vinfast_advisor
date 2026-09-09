"""Unit tests for confirmed-evidence profile projection."""

from uuid import UUID

from src.agents.domain.bottleneck_signal import ConfirmedBottleneckEvidence
from src.agents.domain.customer_profile import Bottleneck, OfferState, ProfileSnapshot
from src.agents.services.profile_snapshot import ProfileSnapshotService


def _evidence(*, signal: int, turn: int, label: Bottleneck, quote: str) -> ConfirmedBottleneckEvidence:
    return ConfirmedBottleneckEvidence(
        signal_id=UUID(f"00000000-0000-0000-0000-{signal:012d}"),
        client_turn_id=UUID(f"10000000-0000-0000-0000-{turn:012d}"),
        turn_number=turn,
        label=label,
        evidence_quote=quote,
    )


class TestProfileSnapshotService:
    def setup_method(self) -> None:
        self.service = ProfileSnapshotService()

    def test_build_projects_slots_and_confirmed_evidence_in_input_order(self) -> None:
        # Given
        slots = {"vehicle_type": "CAR", "budget_max_vnd": "500000000", "color_preference": "red"}
        evidence = (
            _evidence(signal=2, turn=4, label=Bottleneck.RANGE, quote="Tôi thường đi xa"),
            _evidence(signal=1, turn=2, label=Bottleneck.PRICE, quote="Giá vượt ngân sách"),
        )

        # When
        snapshot = self.service.build(slots=slots, confirmed_evidence=evidence)

        # Then
        assert snapshot.needs == ["budget", "vehicle_type"]
        assert [(item.bottleneck, item.verbatim_quote) for item in snapshot.bottlenecks] == [
            (Bottleneck.RANGE, "Tôi thường đi xa"),
            (Bottleneck.PRICE, "Giá vượt ngân sách"),
        ]
        assert snapshot.color_preference == "red"
        assert snapshot.offer_state is OfferState.BOTTLENECK_NO_OFFER

    def test_build_keeps_duplicate_labels_as_distinct_confirmed_evidence(self) -> None:
        # Given
        evidence = (
            _evidence(signal=1, turn=2, label=Bottleneck.PRICE, quote="Giá cao"),
            _evidence(signal=2, turn=3, label=Bottleneck.PRICE, quote="Chi phí vượt mức"),
        )

        # When
        snapshot = self.service.build(slots={}, confirmed_evidence=evidence)

        # Then
        assert [item.verbatim_quote for item in snapshot.bottlenecks] == [
            "Giá cao",
            "Chi phí vượt mức",
        ]

    def test_build_without_confirmed_evidence_has_no_keyword_fallback(self) -> None:
        # Given / When
        snapshot = self.service.build(slots={}, confirmed_evidence=())

        # Then
        assert snapshot.bottlenecks == []
        assert snapshot.offer_state is OfferState.NONE_BOTTLENECK
        assert snapshot.unmet_demand_flag is False

    def test_build_returns_profile_snapshot(self) -> None:
        # Given / When
        snapshot = self.service.build(slots={}, confirmed_evidence=())

        # Then
        assert isinstance(snapshot, ProfileSnapshot)
