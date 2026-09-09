"""Implement `ClockPort` — tách khỏi `datetime.now()` gọi rải rác.

Lý do tồn tại: E2E đóng băng (A9-2) phải cho kết quả giống nhau giữa hai lần
chạy; một `datetime.now()` nằm sâu trong service là đủ để phá tính tái lập.
Test tiêm clock cố định, production dùng `SystemClock`.
"""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Đồng hồ thật, luôn trả giờ UTC có tzinfo."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Đồng hồ đứng yên cho test tất định."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment
