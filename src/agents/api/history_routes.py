"""[A8-3] HTTP cho lịch sử tư vấn — khách xem của mình, tư vấn viên xem khách mình phụ trách."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.agents.api.schemas import SessionHistoryResponse
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.services.operations.history import HistoryAccessDeniedError, HistoryOperations

router = APIRouter(prefix="/agent/history", tags=["agent-history"])


def history_operations() -> HistoryOperations:
    """Điểm nối use case — composition của app thật ghi đè bằng bản có DB."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Chưa nối use case lịch sử tư vấn",
    )


@router.get("/{customer_id}", response_model=list[SessionHistoryResponse])
async def list_customer_history(
    customer_id: str,
    identity: StaffIdentity = Depends(current_staff),
    operations: HistoryOperations = Depends(history_operations),
) -> list[SessionHistoryResponse]:
    """Lịch sử tư vấn của một khách; sai quyền thì 403, không trả dữ liệu rỗng cho qua."""
    try:
        items = await operations.list_for_customer(customer_id, requester_id=identity.staff_id, role=identity.role)
    except HistoryAccessDeniedError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền xem hồ sơ khách này",
        ) from error
    return [SessionHistoryResponse(**vars(item)) for item in items]
