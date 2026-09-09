"""Adapter `ActiveSessionsPort` — mở/đóng session cho từng lời gọi.

Màn Cơ hội bán hàng (C7) chỉ đọc, gọi thưa. Giữ một `AsyncSession` sống suốt
vòng đời app sẽ ghim một connection ở trạng thái "idle in transaction" và chặn
DDL/migration, nên adapter này lấy session từ factory theo từng lời gọi.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationMemoryRepository,
)
from src.agents.ports import ClockPort, SessionSummary


class ActiveSessionsDataSource:
    """Đọc phiên ACTIVE gần đây, một session ngắn cho mỗi lần đọc."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: ClockPort,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def list_active_sessions(self, since: datetime) -> list[SessionSummary]:
        async with self._session_factory() as session:
            repository = SqlAlchemyConversationMemoryRepository(session, clock=self._clock)
            return await repository.list_active_sessions(since)
