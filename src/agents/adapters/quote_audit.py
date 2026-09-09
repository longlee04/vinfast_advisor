"""[A7-4] Đưa việc ghi audit của cổng rủi ro báo giá ra khỏi đường đi của khách.

Chỉ một việc: biến lời ghi thành một task chạy nền, để một lần ghi audit chậm
không cộng thẳng vào thời gian khách phải chờ — rút ngắn đúng thời gian đó là
mục tiêu của A7-4.

Phần biết SQL nằm ở `SqlAlchemyQuoteAuditUnitOfWork` trong `unit_of_work.py`:
`adapters/unit_of_work.py` là nơi DUY NHẤT được mở transaction (mục 6.4).
"""

from __future__ import annotations

import asyncio
import logging

from src.agents.contracts import QuoteAuditRecord
from src.agents.ports import QuoteAuditPort

logger = logging.getLogger(__name__)


class BackgroundQuoteAuditSink:
    """Chạy `inner.record` trong một task nền, nuốt lỗi và log lại.

    Giữ tham chiếu mạnh tới task đang chạy: `asyncio.create_task` chỉ giữ weak
    reference, thả ra thì garbage collector có thể huỷ task giữa chừng và dòng
    audit biến mất im lặng.
    """

    def __init__(self, inner: QuoteAuditPort) -> None:
        self._inner = inner
        self._tasks: set[asyncio.Task[None]] = set()

    async def record(self, entry: QuoteAuditRecord) -> None:
        task = asyncio.create_task(self._write(entry))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _write(self, entry: QuoteAuditRecord) -> None:
        try:
            await self._inner.record(entry)
        except Exception:  # noqa: BLE001 — audit hỏng không được lộ ra phía khách
            logger.exception("quote audit: ghi nền thất bại cho phiên %s", entry.session_id)

    async def drain(self) -> None:
        """Chờ mọi task audit đang chạy — dùng ở `shutdown` và trong test."""

        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)


__all__ = ["BackgroundQuoteAuditSink"]
