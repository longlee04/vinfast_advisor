"""`SqlAlchemyAgentFlagAdapter`: đọc hàng thật, cache TTL 60s, lỗi DB → None."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.agent_flag_repository import SqlAlchemyAgentFlagAdapter
from src.agents.domain.agent_flag import FLAG_AGENT_FALLBACK, AgentFlagState

pytestmark = pytest.mark.asyncio


async def _set(factory: async_sessionmaker[AsyncSession], *, enabled: bool, percent: int = 0, allow: str = "") -> None:
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO agent_feature_flags (name, enabled, rollout_percent, customer_allowlist) "
                "VALUES (:name, :enabled, :percent, :allow) "
                "ON CONFLICT (name) DO UPDATE SET enabled = EXCLUDED.enabled, "
                "rollout_percent = EXCLUDED.rollout_percent, customer_allowlist = EXCLUDED.customer_allowlist"
            ),
            {"name": FLAG_AGENT_FALLBACK, "enabled": enabled, "percent": percent, "allow": allow},
        )


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_ttl_cache_60s(agent_session_factory: async_sessionmaker[AsyncSession]) -> None:
    clock = _Clock()
    await _set(agent_session_factory, enabled=False)
    adapter = SqlAlchemyAgentFlagAdapter(agent_session_factory, ttl_seconds=60.0, clock=clock)
    try:
        first = await adapter.load(FLAG_AGENT_FALLBACK)
        assert first == AgentFlagState(name=FLAG_AGENT_FALLBACK, enabled=False)

        await _set(agent_session_factory, enabled=True, percent=25, allow="c1, c2")
        clock.now += 59.0
        assert (await adapter.load(FLAG_AGENT_FALLBACK)) == first  # còn trong TTL: giá trị cũ

        clock.now += 2.0
        fresh = await adapter.load(FLAG_AGENT_FALLBACK)
        assert fresh == AgentFlagState(
            name=FLAG_AGENT_FALLBACK, enabled=True, rollout_percent=25, customer_allowlist=frozenset({"c1", "c2"})
        )
    finally:
        await _set(agent_session_factory, enabled=False)


async def test_hang_chua_co_thi_none(agent_session_factory: async_sessionmaker[AsyncSession]) -> None:
    adapter = SqlAlchemyAgentFlagAdapter(agent_session_factory)
    assert await adapter.load("co_khong_ton_tai") is None


async def test_db_hong_thi_none_khong_raise() -> None:
    class _BrokenFactory:
        def __call__(self):
            raise RuntimeError("db down")

    adapter = SqlAlchemyAgentFlagAdapter(_BrokenFactory())  # type: ignore[arg-type]
    assert await adapter.load(FLAG_AGENT_FALLBACK) is None
