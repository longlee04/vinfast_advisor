"""agent_0036: bảng `agent_feature_flags` lên/xuống sạch hai chiều, hàng gieo sẵn TẮT."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.agents.integration.conftest import run_alembic


async def _table_exists(database_url: str) -> bool:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return bool(await connection.scalar(text("SELECT to_regclass('public.agent_feature_flags') IS NOT NULL")))
    finally:
        await engine.dispose()


async def _seed_row(database_url: str) -> tuple[bool, int, str] | None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT enabled, rollout_percent, customer_allowlist FROM agent_feature_flags "
                        "WHERE name = 'agent_fallback'"
                    )
                )
            ).first()
            return None if row is None else (bool(row[0]), int(row[1]), str(row[2]))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_downgrade_sach(agent_database_url: str, _agent_migrations_applied: None) -> None:
    """Từ head: bảng có + hàng `agent_fallback` TẮT; downgrade -1 mất bảng; upgrade lại có."""

    assert await _table_exists(agent_database_url)
    assert await _seed_row(agent_database_url) == (False, 0, "")

    completed = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0035")
    assert completed.returncode == 0, completed.stderr
    assert not await _table_exists(agent_database_url)

    completed = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head")
    assert completed.returncode == 0, completed.stderr
    assert await _table_exists(agent_database_url)
    assert await _seed_row(agent_database_url) == (False, 0, "")
