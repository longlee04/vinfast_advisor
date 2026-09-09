"""Unit tests for the customer profile domain (OfferState/Bottleneck/ProfileSnapshot)."""

import pytest
from pydantic import ValidationError

from src.agents.domain.customer_profile import (
    Bottleneck,
    BottleneckEvidence,
    OfferState,
    ProfileSnapshot,
    classify_offer_state,
)


class TestClassifyOfferState:
    """Rule-based classification of the offer state from bottlenecks + matches."""

    def test_empty_bottlenecks_returns_none_bottleneck(self) -> None:
        assert classify_offer_state([], []) == OfferState.NONE_BOTTLENECK
        assert classify_offer_state([], ["anything"]) == OfferState.NONE_BOTTLENECK

    def test_bottlenecks_without_matches_returns_no_offer(self) -> None:
        bottlenecks = [BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="giá cao")]
        assert classify_offer_state(bottlenecks, []) == OfferState.BOTTLENECK_NO_OFFER

    def test_bottlenecks_with_matches_returns_offer_available(self) -> None:
        bottlenecks = [BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="giá cao")]
        matches = ["FIXED_DISCOUNT"]
        assert classify_offer_state(bottlenecks, matches) == OfferState.BOTTLENECK_OFFER_AVAILABLE


class TestProfileSnapshot:
    """Frozen snapshot model and its invariants."""

    def test_snapshot_rejects_invalid_offer_state(self) -> None:
        with pytest.raises(ValidationError):
            ProfileSnapshot(
                needs=[],
                considered_vehicles=[],
                bottlenecks=[],
                offer_state="NOT_A_STATE",  # type: ignore[arg-type]
                unmet_demand_flag=False,
                unmet_bottleneck=None,
                color_preference=None,
            )

    def test_unmet_demand_flag_requires_no_offer_state(self) -> None:
        # unmet_demand_flag=True must only accompany BOTTLENECK_NO_OFFER.
        with pytest.raises(ValidationError):
            ProfileSnapshot(
                needs=[],
                considered_vehicles=[],
                bottlenecks=[BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="giá cao")],
                offer_state=OfferState.BOTTLENECK_OFFER_AVAILABLE,
                unmet_demand_flag=True,
                unmet_bottleneck="PRICE",
                color_preference=None,
            )

    def test_valid_snapshot_is_frozen(self) -> None:
        snapshot = ProfileSnapshot(
            needs=["budget"],
            considered_vehicles=["VF 5"],
            bottlenecks=[BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="giá cao")],
            offer_state=OfferState.BOTTLENECK_OFFER_AVAILABLE,
            unmet_demand_flag=False,
            unmet_bottleneck=None,
            color_preference="red",
        )
        with pytest.raises(ValidationError):
            snapshot.needs = ["extra"]  # type: ignore[misc]
        with pytest.raises(ValidationError):
            snapshot.offer_state = OfferState.NONE_BOTTLENECK  # type: ignore[misc]

    def test_no_offer_state_with_unmet_bottleneck(self) -> None:
        snapshot = ProfileSnapshot(
            needs=[],
            considered_vehicles=[],
            bottlenecks=[BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="giá cao")],
            offer_state=OfferState.BOTTLENECK_NO_OFFER,
            unmet_demand_flag=True,
            unmet_bottleneck="PRICE",
            color_preference=None,
        )
        assert snapshot.unmet_bottleneck == "PRICE"
        assert snapshot.offer_state == OfferState.BOTTLENECK_NO_OFFER
