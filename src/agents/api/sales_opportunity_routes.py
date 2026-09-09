"""[C7] HTTP cho màn Cơ hội bán hàng — phiên đang chạy đã bộc lộ >= 2 nút thắt.

Đường này đọc thẳng từ `SalesOpportunityService`, không chạm `review_queue`: cơ
hội bán hàng là chuyện của phiên đang sống, còn hàng đợi duyệt là chuyện của bản
nháp chờ người thật — trộn hai nguồn lại thì màn nào cũng sai một nửa.

Schema trả về khai ngay tại đây thay vì trong `schemas.py` dùng chung: nó chỉ
phục vụ đúng một route, để chỗ khác thì thành tài sản chung không ai dám sửa.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.agents.api.security import StaffIdentity, require_staff
from src.agents.domain.customer_profile import ProfileSnapshot
from src.agents.services.sales_opportunity import SalesOpportunity

router = APIRouter(prefix="/agent/sales-opportunities", tags=["agent-sales-opportunities"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


class SalesOpportunityPort(Protocol):
    """Chỗ nối use case — chỉ cần đúng một phép đọc."""

    async def list_opportunities(self, at: datetime, limit: int = DEFAULT_LIMIT) -> list: ...


class SalesOpportunityResponse(BaseModel):
    """Một dòng cơ hội bán hàng cho màn tư vấn viên."""

    session_id: str
    customer_id: str
    bottlenecks: list[str]
    snapshot: ProfileSnapshot
    last_active_at: datetime


def sales_opportunity_service() -> SalesOpportunityPort:
    """Điểm nối use case — composition của app thật ghi đè bằng bản có DB."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Chưa nối use case cơ hội bán hàng",
    )


def _response(opportunity: SalesOpportunity) -> SalesOpportunityResponse:
    return SalesOpportunityResponse(
        session_id=opportunity.session_id,
        customer_id=opportunity.customer_id,
        bottlenecks=list(opportunity.bottlenecks),
        snapshot=opportunity.snapshot,
        last_active_at=opportunity.last_active_at,
    )


@router.get("", response_model=list[SalesOpportunityResponse])
async def list_sales_opportunities(
    limit: int = Query(DEFAULT_LIMIT),
    identity: StaffIdentity = Depends(require_staff),
    service: SalesOpportunityPort = Depends(sales_opportunity_service),
) -> list[SalesOpportunityResponse]:
    """Phiên hoạt động gần đây có >= 2 nút thắt, mới hoạt động xếp lên trước."""
    if limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"limit phải trong khoảng 1..{MAX_LIMIT}",
        )
    opportunities = await service.list_opportunities(datetime.now(UTC), limit)
    return [_response(item) for item in opportunities]
