"""Broker sự kiện review theo phiên cho kênh đẩy SSE."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TurnEvent:
    """Sự kiện review đã sẵn sàng gửi tới một phiên khách."""

    session_id: UUID
    review_id: UUID
    kind: str
    event_id: UUID = field(default_factory=uuid4)
    client_turn_id: UUID | None = None
    message_id: UUID | None = None


class TurnEventBroker(Protocol):
    """Kênh phát và đăng ký sự kiện theo phiên."""

    async def publish(self, event: TurnEvent) -> None:
        """Phát sự kiện tới mọi subscriber của phiên."""

    def subscribe(self, session_id: UUID) -> AbstractAsyncContextManager[AsyncIterator[TurnEvent]]:
        """Mở stream sự kiện cho một phiên."""


class InMemoryTurnEventBroker:
    """Bản in-memory — CHỈ ĐÚNG khi ứng dụng chạy MỘT tiến trình.

    `Dockerfile` hiện chạy `uvicorn` không `--workers`, nên bản này đủ. Ngày ai
    đó thêm `--workers 2` hoặc chạy hai instance, tư vấn viên duyệt ở tiến trình
    A còn SSE của khách nằm ở tiến trình B: sự kiện **im lặng không tới**, không
    lỗi, không log. Lúc đó viết bản thứ hai dùng Postgres LISTEN/NOTIFY (asyncpg
    hỗ trợ sẵn) và đổi đúng một dòng ở `composition.py`.
    """

    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[TurnEvent]]] = {}

    async def publish(self, event: TurnEvent) -> None:
        """Phát event tới mọi queue đang nghe cùng phiên."""
        for subscriber in tuple(self._subscribers.get(event.session_id, ())):
            subscriber.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, session_id: UUID) -> AsyncIterator[AsyncIterator[TurnEvent]]:
        """Đăng ký queue và luôn gỡ queue khi stream đóng hoặc bị hủy."""
        subscriber: asyncio.Queue[TurnEvent] = asyncio.Queue()
        subscribers = self._subscribers.setdefault(session_id, set())
        subscribers.add(subscriber)

        async def events() -> AsyncIterator[TurnEvent]:
            while True:
                yield await subscriber.get()

        try:
            yield events()
        finally:
            subscribers.discard(subscriber)
            if not subscribers:
                del self._subscribers[session_id]
