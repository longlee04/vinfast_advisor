"""Chạy việc nền của Customer 360 sau khi lượt khách đã trả lời xong (plan §2.2, G4).

Cùng khuôn `BackgroundQuoteAuditSink`: giữ tham chiếu MẠNH tới task (asyncio chỉ giữ yếu,
GC có thể huỷ giữa chừng), nuốt lỗi và log. Thêm semaphore để một đợt khách đông không
mở hàng trăm lần gọi LLM cùng lúc. Task mất khi process restart thì `sweep` nhặt lại.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from src.agents.logging import get_agent_logger

logger = get_agent_logger("agent.adapters.background_runner")


class BackgroundRunner:
    def __init__(self, *, concurrency: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(self, work: Callable[[], Awaitable[object]], *, label: str) -> None:
        task = asyncio.create_task(self._run(work, label))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, work: Callable[[], Awaitable[object]], label: str) -> None:
        async with self._semaphore:
            try:
                await work()
            except Exception:  # noqa: BLE001 — việc nền hỏng không được chạm tới khách
                logger.warning("background: viec nen that bai label=%s", label.split(":")[0], exc_info=True)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)


__all__ = ["BackgroundRunner"]
