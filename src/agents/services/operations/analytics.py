"""[A9-1] Use case dashboard phễu — đọc view `funnel_metrics` theo khung thời gian.

View đã gộp sẵn theo ngày; service chỉ chọn khoảng ngày, không tính lại số liệu —
tính lại ở hai nơi là cách nhanh nhất để hai nơi lệch nhau.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

#: Khung thời gian dựng sẵn, tính bằng ngày.
PRESET_WINDOWS = {"7d": 7, "30d": 30}
CUSTOM_WINDOW = "custom"


class InvalidWindowError(Exception):
    """Khung thời gian không hợp lệ, hoặc `custom` mà thiếu ngày."""


class ClockPort(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class FunnelRow:
    """Một ngày trong phễu."""

    day: date
    sessions_started: int
    sessions_with_profile: int
    sessions_with_recommendation: int
    sessions_approved: int
    sessions_booked: int


class FunnelStore(Protocol):
    async def read_funnel(self, date_from: date, date_to: date) -> list[FunnelRow]: ...


class AnalyticsTransaction(Protocol):
    analytics: FunnelStore


class AnalyticsUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[AnalyticsTransaction]: ...


def resolve_window(window: str, date_from: date | None, date_to: date | None, today: date) -> tuple[date, date]:
    """Đổi tham số lọc thành khoảng ngày cụ thể; sai thì báo lỗi thay vì đoán."""
    if window in PRESET_WINDOWS:
        return today - timedelta(days=PRESET_WINDOWS[window]), today
    if window == CUSTOM_WINDOW:
        if date_from is None or date_to is None:
            raise InvalidWindowError("custom cần cả date_from và date_to")
        if date_from > date_to:
            raise InvalidWindowError("date_from phải trước date_to")
        return date_from, date_to
    raise InvalidWindowError(window)


class AnalyticsOperations:
    """Use case dashboard phễu (A9-1)."""

    def __init__(self, unit_of_work: AnalyticsUnitOfWork, clock: ClockPort) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def funnel(self, window: str, date_from: date | None = None, date_to: date | None = None) -> list[FunnelRow]:
        start, end = resolve_window(window, date_from, date_to, self._clock.now().date())
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.analytics.read_funnel(start, end)
