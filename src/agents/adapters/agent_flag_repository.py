"""Đọc `agent_feature_flags` qua SQLAlchemy, cache TTL 60s (plan agent-migration Bước 3).

Cùng khuôn `_DIRECTORY_CACHE` của `core/run_turn.py`: giá trị đọc được giữ
trong tiến trình đúng `ttl_seconds`, hết hạn mới hỏi DB lại. Bật/tắt bằng
`UPDATE` có hiệu lực trong vòng một TTL, không cần restart.

KHÔNG raise: DB hỏng → log cảnh báo, trả `None` (= TẮT) và cũng cache `None`
để một sự cố DB không biến thành một truy vấn lỗi mỗi lượt.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.domain.agent_flag import FLAG_TTL_SECONDS, AgentFlagState, parse_allowlist
from src.agents.logging import get_agent_logger
from src.agents.models import AgentFeatureFlagRow

logger = get_agent_logger("agent.adapters.agent_flag")


class SqlAlchemyAgentFlagAdapter:
    """`AgentFlagPort` trên bảng `agent_feature_flags`."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        ttl_seconds: float = FLAG_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, AgentFlagState | None]] = {}

    async def load(self, name: str) -> AgentFlagState | None:
        now = self._clock()
        cached = self._cache.get(name)
        if cached is not None and now < cached[0]:
            return cached[1]
        state = await self._read(name)
        self._cache[name] = (now + self._ttl, state)
        return state

    def invalidate(self, name: str | None = None) -> None:
        """Xoá cache (một cờ hoặc tất cả). Dùng cho test và script vận hành."""

        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)

    async def _read(self, name: str) -> AgentFlagState | None:
        try:
            async with self._session_factory() as session:
                row = (
                    await session.execute(select(AgentFeatureFlagRow).where(AgentFeatureFlagRow.name == name))
                ).scalar_one_or_none()
        except Exception:
            logger.warning("agent.flag khong doc duoc co name=%s, coi nhu TAT", name, exc_info=True)
            return None
        if row is None:
            return None
        return AgentFlagState(
            name=row.name,
            enabled=bool(row.enabled),
            rollout_percent=int(row.rollout_percent),
            customer_allowlist=parse_allowlist(row.customer_allowlist),
        )


__all__ = ["SqlAlchemyAgentFlagAdapter"]
