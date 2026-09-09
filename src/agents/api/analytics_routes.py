"""[A9-1] HTTP cho dashboard phễu — lọc 7 ngày / 30 ngày / tuỳ chỉnh."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.agents.api.schemas import FunnelRowResponse
from src.agents.api.security import StaffIdentity, require_admin
from src.agents.services.operations.analytics import AnalyticsOperations, InvalidWindowError

router = APIRouter(prefix="/agent/analytics", tags=["agent-analytics"])


def analytics_operations() -> AnalyticsOperations:
    """Điểm nối use case — composition của app thật ghi đè bằng bản có DB."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Chưa nối use case dashboard phễu",
    )


@router.get("/funnel", response_model=list[FunnelRowResponse])
async def read_funnel(
    window: str = Query(default="7d", description="7d | 30d | custom"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    identity: StaffIdentity = Depends(require_admin),
    operations: AnalyticsOperations = Depends(analytics_operations),
) -> list[FunnelRowResponse]:
    """Số liệu phễu theo ngày trong khung thời gian đã chọn."""
    try:
        rows = await operations.funnel(window, date_from=date_from, date_to=date_to)
    except InvalidWindowError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Khung thời gian không hợp lệ: {error}",
        ) from error
    return [FunnelRowResponse(**vars(row)) for row in rows]
