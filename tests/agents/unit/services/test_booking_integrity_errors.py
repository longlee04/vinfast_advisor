"""Chỉ ĐÚNG một vi phạm ràng buộc mới có nghĩa là "khung giờ đã đầy".

Bản vá chống đua đầu tiên bắt MỌI `IntegrityError` rồi trả `None`. `None` được
`chain._book_test_drive` đọc thành câu *"khung giờ này vừa có người đặt mất"* —
nên một lỗi khoá ngoại, một cột `NOT NULL` bỏ trống, hay một `CHECK` sai đều bị
kể lại cho khách như chuyện chỗ đã kín. Lỗi dữ liệu bị giấu sau một câu trấn an
là lỗi không ai đi tìm.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.agents.services.test_drive import SLOT_UNIQUE_INDEX, BookingUnitOfWorkSlotCounter

SHOWROOM = "VinFast Long Biên"
SLOT = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
VEHICLE = uuid4()


def _integrity_error(constraint: str | None) -> IntegrityError:
    class _OrigError(Exception):
        constraint_name = constraint

    return IntegrityError("INSERT ...", None, _OrigError("vi pham rang buoc"))


class _Bookings:
    def __init__(self, error: IntegrityError) -> None:
        self._error = error

    async def booking_of(self, *, customer_id: str, showroom: str, scheduled_at: datetime) -> UUID | None:
        return None

    async def count_active_at(self, showroom: str, scheduled_at: datetime) -> int:
        return 0

    async def create_booking(self, **kwargs) -> UUID:
        raise self._error


class _Transaction:
    def __init__(self, error: IntegrityError) -> None:
        self.bookings = _Bookings(error)
        self.notices = None


class _UnitOfWork:
    def __init__(self, error: IntegrityError) -> None:
        self._error = error

    def transaction(self):
        error = self._error

        class _Ctx:
            async def __aenter__(self):
                return _Transaction(error)

            async def __aexit__(self, *exc_info):
                return False

        return _Ctx()


def _booker(error: IntegrityError) -> BookingUnitOfWorkSlotCounter:
    return BookingUnitOfWorkSlotCounter(_UnitOfWork(error))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dung_rang_buoc_khung_gio_thi_tra_none() -> None:
    """Đua thật ở đúng index sức chứa ⇒ "khung vừa đầy"."""

    booker = _booker(_integrity_error(SLOT_UNIQUE_INDEX))

    result = await booker.book(customer_id="khach-1", vehicle_id=VEHICLE, showroom=SHOWROOM, scheduled_at=SLOT)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "constraint",
    ["fk_test_drive_bookings_run", "ck_test_drive_bookings_status", None],
)
async def test_rang_buoc_khac_phai_noi_len_khong_duoc_nuot(constraint: str | None) -> None:
    """Lỗi dữ liệu KHÔNG được kể lại cho khách như chuyện chỗ đã kín."""

    booker = _booker(_integrity_error(constraint))

    with pytest.raises(IntegrityError):
        await booker.book(customer_id="khach-1", vehicle_id=VEHICLE, showroom=SHOWROOM, scheduled_at=SLOT)
