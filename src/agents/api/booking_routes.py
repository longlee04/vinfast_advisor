"""[A8-2] HTTP cho đặt lịch lái thử — kết nối trực tiếp database PostgreSQL."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.agents.api.dependencies import CustomerDependency
from src.agents.api.schemas import (
    BookingListItemResponse,
    BookTestDriveRequest,
    BookTestDriveResponse,
)
from src.agents.api.security import StaffIdentity, optional_staff, require_staff
from src.agents.services.operations.booking import (
    BookingOperations,
    RunNotApprovedError,
    RunNotFoundError,
    SlotFullError,
)

router = APIRouter(prefix="/agent/bookings", tags=["agent-bookings"])


def booking_operations() -> BookingOperations:
    """Điểm nối use case — composition của app thật ghi đè bằng bản có DB."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Chưa nối use case đặt lịch lái thử",
    )


@router.get("/options")
async def get_booking_options(
    operations: BookingOperations = Depends(booking_operations),
) -> dict:
    """Lấy danh sách xe và showroom thực tế từ PostgreSQL cho bộ chọn đặt lịch."""
    return await operations.get_options()


@router.get("", response_model=list[BookingListItemResponse])
async def list_bookings(
    status_filter: str | None = None,
    identity: StaffIdentity = Depends(require_staff),
    operations: BookingOperations = Depends(booking_operations),
) -> list[BookingListItemResponse]:
    """Danh sách các yêu cầu đặt lịch lái thử cho Advisor và Admin (PostgreSQL)."""
    rows = await operations.list_bookings(status=status_filter)
    return [
        BookingListItemResponse(
            booking_id=r.booking_id,
            customer_id=r.customer_id,
            customer_name=r.customer_name,
            phone=r.phone,
            vehicle_id=r.vehicle_id,
            vehicle_name=r.vehicle_name,
            advisor_id=r.advisor_id,
            showroom=r.showroom,
            scheduled_at=r.scheduled_at,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/me", response_model=list[BookingListItemResponse])
async def list_my_bookings(
    customer_id: str | None = CustomerDependency,
    operations: BookingOperations = Depends(booking_operations),
) -> list[BookingListItemResponse]:
    """Lịch lái thử của CHÍNH khách đang đăng nhập — trang tài khoản khách hàng.

    Khai báo TRƯỚC mọi route `/{booking_id}` để `/me` không bị nuốt thành một
    `booking_id`. Không có endpoint hủy tương ứng cho khách — hủy vẫn chỉ dành
    cho nhân sự qua `require_staff`.
    """
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập")
    rows = await operations.list_for_customer(customer_id=customer_id)
    return [
        BookingListItemResponse(
            booking_id=r.booking_id,
            customer_id=r.customer_id,
            customer_name=r.customer_name,
            phone=r.phone,
            vehicle_id=r.vehicle_id,
            vehicle_name=r.vehicle_name,
            advisor_id=r.advisor_id,
            showroom=r.showroom,
            scheduled_at=r.scheduled_at,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BookTestDriveResponse)
async def book_test_drive(
    payload: BookTestDriveRequest,
    customer_id: str | None = CustomerDependency,
    staff: StaffIdentity | None = Depends(optional_staff),
    operations: BookingOperations = Depends(booking_operations),
) -> BookTestDriveResponse:
    """Đặt lịch lái thử từ Customer portal hoặc qua đề xuất."""
    # Direct portal booking without run_id
    if payload.run_id is None:
        target_customer_id = customer_id or payload.customer_id or payload.phone or "customer-portal"
        booking_id = await operations.book_direct(
            customer_id=target_customer_id,
            vehicle_id=payload.vehicle_id,
            showroom=payload.showroom,
            scheduled_at=payload.scheduled_at,
            customer_name=payload.customer_name,
            phone=payload.phone,
        )
        return BookTestDriveResponse(booking_id=booking_id)

    # Flow booking with run_id
    advisor_id = staff.staff_id if staff else (customer_id or "system")
    try:
        booking_id = await operations.book(
            run_id=payload.run_id,
            vehicle_id=payload.vehicle_id,
            advisor_id=advisor_id,
            showroom=payload.showroom,
            scheduled_at=payload.scheduled_at,
        )
    except RunNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đề xuất") from error
    except RunNotApprovedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đề xuất chưa được duyệt, chưa đặt lịch được",
        ) from error
    except SlotFullError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Khung giờ này ở showroom đã đầy",
        ) from error
    return BookTestDriveResponse(booking_id=booking_id)


@router.post("/{booking_id}/confirm")
async def confirm_booking(
    booking_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: BookingOperations = Depends(booking_operations),
) -> dict:
    """Advisor xác nhận lịch hẹn lái thử của khách hàng."""
    success = await operations.confirm_booking(booking_id=booking_id, advisor_id=identity.staff_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lịch hẹn")
    return {"confirmed": True, "booking_id": booking_id}


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: BookingOperations = Depends(booking_operations),
) -> dict:
    """Hủy lịch hẹn lái thử."""
    success = await operations.cancel_booking(booking_id=booking_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lịch hẹn")
    return {"cancelled": True, "booking_id": booking_id}
