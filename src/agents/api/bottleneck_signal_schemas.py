"""Safe HTTP schemas for staff bottleneck signal workflow."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BottleneckSignalResponse(BaseModel):
    """Staff-safe signal projection excluding detector provenance metadata."""

    model_config = ConfigDict(frozen=True)

    signal_id: UUID
    session_id: UUID
    client_turn_id: UUID
    anchor_client_turn_id: UUID
    label: str
    evidence_quote: str
    status: str
    claimed_by: str | None
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    advisor_id: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BottleneckSignalDetailResponse(BottleneckSignalResponse):
    matched_promotions: list[dict] = Field(default_factory=list)
    adjustment_policies: list[dict] = Field(default_factory=list)


class BottleneckSignalOfferRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    promotion_code: str
    promotion_type: str
    adjustment_type: str = "VND"
    amount_vnd: int | None = None
    percent: str | None = None
    months: int | None = None
    gift_code: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None


class BottleneckSignalOfferResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: UUID


class BottleneckSignalVerdictRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Literal["CORRECT", "INCORRECT"]
