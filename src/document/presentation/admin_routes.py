"""FastAPI Admin Review routes for Gate A10 (A10-5)."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.domain.authorization import Role
from src.document.infrastructure.models import VehicleDocumentRow
from src.document.presentation.dependencies import CurrentPrincipal, get_current_principal
from src.products.infrastructure.models import VehicleFeatureFlagRow


class FeatureProposalItem(BaseModel):
    vehicle_id: str
    feature_code: str
    status: str
    verification_status: str
    confidence: float | None = None
    evidence_citation: str | None = None


class PendingProposalsGroupedResponse(BaseModel):
    total_count: int
    items: list[FeatureProposalItem]


class ReviewActionRequest(BaseModel):
    vehicle_id: str
    feature_code: str
    action: str = Field(..., description="APPROVE or REJECT")


class ReviewActionResult(BaseModel):
    vehicle_id: str
    feature_code: str
    verification_status: str
    message: str


router = APIRouter(prefix="/admin/feature-flags", tags=["admin-brochure-review"])


def _require_admin(principal: CurrentPrincipal) -> CurrentPrincipal:
    """Enforce strict ADMIN-only authorization policy (PRD 5.11 AC)."""
    if principal.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to review feature flag proposals",
        )
    return principal


@router.get("/pending", response_model=PendingProposalsGroupedResponse)
async def list_pending_feature_proposals(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(lambda: None)],  # Overridden or injected
) -> PendingProposalsGroupedResponse:
    """List pending feature flag proposals grouped by vehicle with brochure evidence citations (A10-5)."""
    _require_admin(principal)

    stmt = select(VehicleFeatureFlagRow).where(VehicleFeatureFlagRow.verification_status == "PENDING")
    res = await session.execute(stmt)
    pending_rows = res.scalars().all()

    items: list[FeatureProposalItem] = []

    for row in pending_rows:
        # Fetch citation evidence from brochure chunks
        doc_stmt = (
            select(VehicleDocumentRow)
            .where(
                VehicleDocumentRow.vehicle_id == row.vehicle_id,
                VehicleDocumentRow.document_type == "BROCHURE",
            )
            .limit(1)
        )
        doc_res = await session.execute(doc_stmt)
        v_doc = doc_res.scalar_one_or_none()
        citation = f"{v_doc.title} (p.{v_doc.page_number})" if v_doc else "Brochure evidence"

        items.append(
            FeatureProposalItem(
                vehicle_id=row.vehicle_id,
                feature_code=row.feature_code,
                status=row.status,
                verification_status=row.verification_status,
                confidence=float(row.confidence) if row.confidence is not None else 0.85,
                evidence_citation=citation,
            )
        )

    return PendingProposalsGroupedResponse(total_count=len(items), items=items)


@router.post("/review", response_model=ReviewActionResult)
async def review_feature_proposal(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    request: ReviewActionRequest,
    session: Annotated[AsyncSession, Depends(lambda: None)],
) -> ReviewActionResult:
    """Approve or Reject a PENDING feature proposal (A10-5). Only ADMIN role permitted."""
    _require_admin(principal)

    action_upper = request.action.upper()
    if action_upper not in ("APPROVE", "REJECT"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Action must be APPROVE or REJECT",
        )

    stmt = select(VehicleFeatureFlagRow).where(
        VehicleFeatureFlagRow.vehicle_id == request.vehicle_id,
        VehicleFeatureFlagRow.feature_code == request.feature_code,
    )
    res = await session.execute(stmt)
    flag_row = res.scalar_one_or_none()

    if flag_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag for vehicle {request.vehicle_id} and feature {request.feature_code} not found",
        )

    now_utc = datetime.datetime.now(datetime.UTC)

    if action_upper == "APPROVE":
        flag_row.verification_status = "APPROVED"
        flag_row.updated_at = now_utc
        msg = "Feature proposal APPROVED and immediately available for advisory queries"
    else:
        flag_row.verification_status = "REJECTED"
        flag_row.updated_at = now_utc
        msg = "Feature proposal REJECTED and excluded from advisory queries"

    await session.flush()

    return ReviewActionResult(
        vehicle_id=flag_row.vehicle_id,
        feature_code=flag_row.feature_code,
        verification_status=flag_row.verification_status,
        message=msg,
    )
