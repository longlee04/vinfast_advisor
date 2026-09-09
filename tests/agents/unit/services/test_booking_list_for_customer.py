"""[Ráp 3] `BookingOperations.list_for_customer` chỉ trả lịch của đúng khách.

Cùng kiểu fake unit-of-work với `test_booking_integrity_errors.py` — không cần
Postgres, chỉ xác nhận use case gọi đúng tầng lưu trữ với đúng tham số lọc.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.agents.services.operations.booking import BookingDto, BookingOperations

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


class _Bookings:
    def __init__(self, dtos: list[BookingDto]) -> None:
        self._dtos = dtos
        self.seen_customer_id: str | None = None

    async def list_for_customer(self, customer_id: str) -> list[BookingDto]:
        self.seen_customer_id = customer_id
        return self._dtos


class _Transaction:
    def __init__(self, bookings: _Bookings) -> None:
        self.bookings = bookings
        self.notices = None


class _UnitOfWork:
    def __init__(self, bookings: _Bookings) -> None:
        self._bookings = bookings

    def transaction(self):
        bookings = self._bookings

        class _Ctx:
            async def __aenter__(self):
                return _Transaction(bookings)

            async def __aexit__(self, *exc_info):
                return False

        return _Ctx()


def _dto(customer_id: str) -> BookingDto:
    return BookingDto(
        booking_id=uuid4(),
        customer_id=customer_id,
        vehicle_id=uuid4(),
        vehicle_name="VinFast VF8",
        advisor_id=None,
        showroom="VinFast Long Biên",
        scheduled_at=NOW,
        status="REQUESTED",
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_list_for_customer_forwards_the_calling_customer_id() -> None:
    """Use case phải truyền đúng `customer_id` xuống tầng lưu trữ để lọc."""

    expected = _dto("customer-1")
    bookings = _Bookings([expected])
    operations = BookingOperations(unit_of_work=_UnitOfWork(bookings))  # type: ignore[arg-type]

    result = await operations.list_for_customer(customer_id="customer-1")

    assert bookings.seen_customer_id == "customer-1"
    assert result == [expected]


@pytest.mark.asyncio
async def test_list_for_customer_never_asks_for_someone_elses_bookings() -> None:
    """Khách A gọi thì tham số lọc phải là khách A, không lẫn khách khác."""

    bookings = _Bookings([])
    operations = BookingOperations(unit_of_work=_UnitOfWork(bookings))  # type: ignore[arg-type]

    await operations.list_for_customer(customer_id="customer-2")

    assert bookings.seen_customer_id == "customer-2"
    assert bookings.seen_customer_id != "customer-1"
