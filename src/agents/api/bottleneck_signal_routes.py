"""Staff-only HTTP routes for bottleneck signal verification."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.agents.api.bottleneck_signal_schemas import (
    BottleneckSignalDetailResponse,
    BottleneckSignalOfferRequest,
    BottleneckSignalOfferResponse,
    BottleneckSignalResponse,
    BottleneckSignalVerdictRequest,
)
from src.agents.api.security import StaffIdentity, require_staff
from src.agents.domain.bottleneck_signal import (
    BottleneckSignal,
    BottleneckSignalStatus,
    SignalClaimDeniedError,
    SignalNotFoundError,
    SignalVerdict,
)
from src.agents.domain.pii import redact_pii
from src.agents.services.operations.bottleneck_signal import (
    BottleneckSignalOperations,
    SignalOfferConflictError,
)
from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentOutOfBoundsError,
    PromotionExpiredError,
)

router = APIRouter(prefix="/agent/bottleneck-signals", tags=["agent-bottleneck-signals"])


def bottleneck_signal_operations() -> BottleneckSignalOperations:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Bottleneck signal operations unavailable",
    )


def _response(signal: BottleneckSignal) -> BottleneckSignalResponse:
    return BottleneckSignalResponse(
        signal_id=signal.signal_id,
        session_id=signal.session_id,
        client_turn_id=signal.client_turn_id,
        anchor_client_turn_id=signal.anchor_client_turn_id,
        label=signal.label.value,
        # Màn nội bộ ghi "đã lược danh tính" — phải che thật SĐT/email khách gõ vào.
        evidence_quote=redact_pii(signal.evidence_quote),
        status=signal.status.value,
        claimed_by=signal.claimed_by,
        claimed_at=signal.claimed_at,
        lease_expires_at=signal.lease_expires_at,
        advisor_id=signal.advisor_id,
        decided_at=signal.decided_at,
        created_at=signal.created_at,
        updated_at=signal.updated_at,
    )


def _claim_conflict(error: SignalClaimDeniedError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="signal_not_claimable_or_lease_invalid",
    )


def _not_found(error: SignalNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")


@router.get("", response_model=list[BottleneckSignalResponse])
async def list_signals(
    signal_status: Literal["pending", "correct", "incorrect"] = Query("pending", alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    identity: StaffIdentity = Depends(require_staff),
    operations: BottleneckSignalOperations = Depends(bottleneck_signal_operations),
) -> list[BottleneckSignalResponse]:
    signals = await operations.list_signals(BottleneckSignalStatus(signal_status.upper()), limit, offset)
    return [_response(signal) for signal in signals]


@router.get("/{signal_id}", response_model=BottleneckSignalDetailResponse)
async def signal_detail(
    signal_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: BottleneckSignalOperations = Depends(bottleneck_signal_operations),
) -> BottleneckSignalDetailResponse:
    try:
        detail = await operations.detail(signal_id)
    except SignalNotFoundError as error:
        raise _not_found(error) from error
    base = _response(detail.signal)
    return BottleneckSignalDetailResponse(
        **base.model_dump(),
        matched_promotions=list(detail.matched_promotions),
        adjustment_policies=list(detail.adjustment_policies),
    )


@router.post("/{signal_id}/offer", response_model=BottleneckSignalOfferResponse)
async def submit_signal_offer(
    signal_id: UUID,
    payload: BottleneckSignalOfferRequest,
    identity: StaffIdentity = Depends(require_staff),
    operations: BottleneckSignalOperations = Depends(bottleneck_signal_operations),
) -> BottleneckSignalOfferResponse:
    try:
        await operations.submit_offer(
            signal_id,
            identity.staff_id,
            OfferAdjustment(**payload.model_dump()),
        )
    except SignalNotFoundError as error:
        raise _not_found(error) from error
    except SignalOfferConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="signal_offer_unavailable",
        ) from error
    except PromotionExpiredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="promotion_expired",
        ) from error
    except OfferAdjustmentOutOfBoundsError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="adjustment_out_of_bounds",
        ) from error
    return BottleneckSignalOfferResponse(signal_id=signal_id)


@router.post("/{signal_id}/claim", response_model=BottleneckSignalResponse)
async def claim_signal(
    signal_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: BottleneckSignalOperations = Depends(bottleneck_signal_operations),
) -> BottleneckSignalResponse:
    try:
        signal = await operations.claim(signal_id, identity.staff_id)
    except SignalNotFoundError as error:
        raise _not_found(error) from error
    except SignalClaimDeniedError as error:
        raise _claim_conflict(error) from error
    return _response(signal)


@router.post("/{signal_id}/verdict", response_model=BottleneckSignalResponse)
async def decide_signal(
    signal_id: UUID,
    payload: BottleneckSignalVerdictRequest,
    identity: StaffIdentity = Depends(require_staff),
    operations: BottleneckSignalOperations = Depends(bottleneck_signal_operations),
) -> BottleneckSignalResponse:
    try:
        signal = await operations.verdict(signal_id, identity.staff_id, SignalVerdict(payload.verdict))
    except SignalNotFoundError as error:
        raise _not_found(error) from error
    except SignalClaimDeniedError as error:
        raise _claim_conflict(error) from error
    return _response(signal)
