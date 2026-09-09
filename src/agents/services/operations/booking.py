"""[A8-2] Use case đặt lịch lái thử.

Booking và thông báo in-app ghi trong **cùng một** transaction — đây là thứ thay
cho cơ chế outbox đã cắt: hỏng ở bước sau thì bước trước cũng không còn, không để
lại booking mồ côi mà không ai được báo.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

#: Mỗi showroom nhận tối đa bấy nhiêu lượt lái thử trong cùng một khung giờ.
SLOT_CAPACITY = 1

#: Chỉ run đã duyệt mới được đặt lịch — cùng cột trạng thái mà A7-3 dùng.
BOOKABLE_REVIEW_STATUSES = frozenset({"APPROVED", "EDITED"})


class RunNotFoundError(Exception):
    """Không có run nào ứng với mã đã gửi."""


class RunNotApprovedError(Exception):
    """Run chưa được duyệt mà đã đòi đặt lịch."""


class SlotFullError(Exception):
    """Khung giờ ở showroom đó đã đầy."""


@dataclass(frozen=True)
class BookableRun:
    """Run kèm thông tin cần để đặt lịch."""

    run_id: UUID
    customer_id: str
    review_status: str


@dataclass(frozen=True)
class BookingDto:
    booking_id: UUID
    customer_id: str
    vehicle_id: UUID
    vehicle_name: str
    advisor_id: str | None
    showroom: str
    scheduled_at: datetime
    status: str
    created_at: datetime
    customer_name: str | None = None
    phone: str | None = None


class BookingStore(Protocol):
    """Phần dữ liệu đặt lịch mà use case này cần."""

    async def find_run(self, run_id: UUID) -> BookableRun | None: ...

    async def count_active_at(self, showroom: str, scheduled_at: datetime) -> int: ...

    async def busy_slots_between(self, *, showroom: str, start: datetime, end: datetime) -> list[datetime]: ...

    async def create_booking(
        self,
        *,
        run_id: UUID | None = None,
        customer_id: str,
        vehicle_id: UUID,
        advisor_id: str | None = None,
        showroom: str,
        scheduled_at: datetime,
    ) -> UUID: ...

    async def list_bookings(self, status: str | None = None, advisor_id: str | None = None) -> list[BookingDto]: ...

    async def list_for_customer(self, customer_id: str) -> list[BookingDto]: ...

    async def confirm_booking(self, booking_id: UUID, advisor_id: str) -> bool: ...

    async def cancel_booking(self, booking_id: UUID) -> bool: ...

    async def get_options(self) -> dict: ...


class NoticeWriter(Protocol):
    async def create_notice(self, title: str, content: str, priority: str, created_by: str) -> UUID: ...


class BookingTransaction(Protocol):
    bookings: BookingStore
    notices: NoticeWriter


class BookingUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[BookingTransaction]: ...


class BookingOperations:
    """Use case đặt lịch lái thử (A8-2)."""

    def __init__(self, unit_of_work: BookingUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def book(
        self,
        *,
        run_id: UUID,
        vehicle_id: UUID,
        advisor_id: str,
        showroom: str,
        scheduled_at: datetime,
    ) -> UUID:
        """Đặt lịch từ một đề xuất đã duyệt; booking và thông báo cùng một transaction."""
        async with self._unit_of_work.transaction() as transaction:
            run = await transaction.bookings.find_run(run_id)
            if run is None:
                raise RunNotFoundError(str(run_id))
            if run.review_status not in BOOKABLE_REVIEW_STATUSES:
                raise RunNotApprovedError(str(run_id))
            # KHÔNG còn chặn khung đã có người (Sếp 2026-08-31: bỏ giới hạn đặt
            # lịch — bao nhiêu khách một khung cũng nhận). `SlotFullError` giữ
            # lại cho route cũ bắt, nhưng không đường nào ném nữa.
            booking_id = await transaction.bookings.create_booking(
                run_id=run_id,
                customer_id=run.customer_id,
                vehicle_id=vehicle_id,
                advisor_id=advisor_id,
                showroom=showroom,
                scheduled_at=scheduled_at,
            )
            await transaction.notices.create_notice(
                title="Lịch lái thử mới",
                content=(f"Khách {run.customer_id} đặt lái thử tại {showroom} lúc {scheduled_at.isoformat()}"),
                priority="NORMAL",
                created_by=advisor_id,
            )
            return booking_id

    async def book_direct(
        self,
        *,
        customer_id: str,
        vehicle_id: UUID,
        showroom: str,
        scheduled_at: datetime,
        customer_name: str | None = None,
        phone: str | None = None,
    ) -> UUID:
        """Đặt lịch trực tiếp từ Customer portal."""
        async with self._unit_of_work.transaction() as transaction:
            booking_id = await transaction.bookings.create_booking(
                run_id=None,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                advisor_id=None,
                showroom=showroom,
                scheduled_at=scheduled_at,
            )
            name_str = customer_name or customer_id
            await transaction.notices.create_notice(
                title="Yêu cầu lái thử mới từ khách hàng",
                content=f"Khách hàng {name_str} ({phone or 'Chưa có SĐT'}) vừa đặt lịch lái thử xe tại Showroom {showroom} vào lúc {scheduled_at.strftime('%d/%m/%Y %H:%M')}.",
                priority="URGENT",
                created_by="customer",
            )
            return booking_id

    async def list_bookings(self, status: str | None = None, advisor_id: str | None = None) -> list[BookingDto]:
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.bookings.list_bookings(status=status, advisor_id=advisor_id)

    async def list_for_customer(self, customer_id: str) -> list[BookingDto]:
        """Lịch lái thử của MỘT khách — dùng cho trang tài khoản của khách (`/me`)."""
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.bookings.list_for_customer(customer_id=customer_id)

    async def confirm_booking(self, booking_id: UUID, advisor_id: str) -> bool:
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.bookings.confirm_booking(booking_id=booking_id, advisor_id=advisor_id)

    async def cancel_booking(self, booking_id: UUID) -> bool:
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.bookings.cancel_booking(booking_id=booking_id)

    async def get_options(self) -> dict:
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.bookings.get_options()
