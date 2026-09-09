"""Customer profile domain: offer state, bottlenecks and the frozen snapshot.

Pure Python — no SQLAlchemy or FastAPI imports, so it stays usable from both
the agent services and the products offer-matching modules.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OfferState(StrEnum):
    """Three-way offer state for one captured customer profile."""

    NONE_BOTTLENECK = "NONE_BOTTLENECK"
    BOTTLENECK_NO_OFFER = "BOTTLENECK_NO_OFFER"
    BOTTLENECK_OFFER_AVAILABLE = "BOTTLENECK_OFFER_AVAILABLE"


class Bottleneck(StrEnum):
    """Customer concern detected from the transcript."""

    PRICE = "PRICE"
    CHARGING = "CHARGING"
    BATTERY = "BATTERY"
    RANGE = "RANGE"


class BottleneckEvidence(BaseModel):
    """One detected bottleneck with the customer's verbatim quote."""

    model_config = ConfigDict(frozen=True)

    bottleneck: Bottleneck
    verbatim_quote: str


class ProfileSnapshot(BaseModel):
    """Immutable profile captured at enqueue time.

    Invariant: ``unmet_demand_flag=True`` may only accompany
    ``offer_state=BOTTLENECK_NO_OFFER`` (a need with no matching offer).
    """

    model_config = ConfigDict(frozen=True)

    needs: list[str] = Field(default_factory=list)
    considered_vehicles: list[str] = Field(default_factory=list)
    bottlenecks: list[BottleneckEvidence] = Field(default_factory=list)
    matched_promotions: list[dict] = Field(default_factory=list)
    # Guard 1A: các cụm chữ số đã verify (từ VehicleFacts) — chống approve nguyên
    # trạng chứa số rác không traceable.
    verified_number_tokens: list[str] = Field(default_factory=list)
    offer_state: OfferState
    unmet_demand_flag: bool = False
    unmet_bottleneck: str | None = None
    color_preference: str | None = None

    @model_validator(mode="after")
    def _check_unmet_demand_invariant(self) -> ProfileSnapshot:
        if self.unmet_demand_flag and self.offer_state != OfferState.BOTTLENECK_NO_OFFER:
            raise ValueError("unmet_demand_flag=True requires offer_state=BOTTLENECK_NO_OFFER")
        return self


def classify_offer_state(
    bottlenecks: Sequence[BottleneckEvidence],
    matched_promotions: Sequence[object],
) -> OfferState:
    """Classify the three-way offer state from detected bottlenecks and matches."""

    if not bottlenecks:
        return OfferState.NONE_BOTTLENECK
    if not matched_promotions:
        return OfferState.BOTTLENECK_NO_OFFER
    return OfferState.BOTTLENECK_OFFER_AVAILABLE
