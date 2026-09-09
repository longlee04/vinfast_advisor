"""[A8-4] HTTP cho thông báo nội bộ — đăng (Admin), xem và đánh dấu đã đọc (nhân sự)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.agents.api.schemas import NoticeResponse, PublishNoticeRequest, PublishNoticeResponse
from src.agents.api.security import StaffIdentity, require_admin, require_staff
from src.agents.services.operations.notices import NoticeNotFoundError, NoticeOperations

router = APIRouter(prefix="/agent/notices", tags=["agent-notices"])


def notice_operations() -> NoticeOperations:
    """Điểm nối use case — composition của app thật ghi đè bằng bản có DB."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Chưa nối use case thông báo nội bộ",
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PublishNoticeResponse)
async def publish_notice(
    payload: PublishNoticeRequest,
    identity: StaffIdentity = Depends(require_admin),
    operations: NoticeOperations = Depends(notice_operations),
) -> PublishNoticeResponse:
    """Đăng thông báo — chỉ Admin."""
    notice_id = await operations.publish(
        title=payload.title,
        content=payload.content,
        priority=payload.priority,
        created_by=identity.staff_id,
    )
    return PublishNoticeResponse(notice_id=notice_id)


@router.get("", response_model=list[NoticeResponse])
async def list_notices(
    identity: StaffIdentity = Depends(require_staff),
    operations: NoticeOperations = Depends(notice_operations),
) -> list[NoticeResponse]:
    """Danh sách thông báo kèm cờ đã đọc của riêng người đang đăng nhập."""
    summaries = await operations.list_for(advisor_id=identity.staff_id)
    return [NoticeResponse(**vars(summary)) for summary in summaries]


@router.post("/{notice_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notice_read(
    notice_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: NoticeOperations = Depends(notice_operations),
) -> None:
    """Đánh dấu đã đọc cho riêng người gọi — hành động tường minh, không tự động khi xem."""
    try:
        await operations.mark_read(notice_id, advisor_id=identity.staff_id)
    except NoticeNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thông báo") from error
