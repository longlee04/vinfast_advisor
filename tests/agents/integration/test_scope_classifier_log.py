"""Real PostgreSQL audit test for the A6-2 scope classifier."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.unit_of_work import SqlAlchemyScopeLogUnitOfWork
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.values import ScopeLabel
from src.agents.services.scope_classifier import DefaultScopeClassifierService

SESSION_ID = UUID("10000000-0000-0000-0000-000000000101")
LOG_ID = UUID("20000000-0000-0000-0000-000000000101")
NOW = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FixedContext:
    def current_session_id(self) -> UUID:
        return SESSION_ID


class CompetitorClassifier:
    async def classify_scope(self, *, prompt: str) -> str:
        assert "Tesla" in prompt
        return ScopeLabel.OUT_OF_SCOPE.value


@pytest.mark.asyncio
async def test_competitor_classification_persists_complete_audit_row(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO conversation_sessions "
                "(session_id, customer_id, status, started_at, last_activity_at, "
                "created_at, updated_at) VALUES "
                "(:session_id, 'customer', 'ACTIVE', :now, :now, :now, :now)"
            ),
            {"session_id": SESSION_ID, "now": NOW},
        )
    adapter = SqlAlchemyScopeLogUnitOfWork(
        session_factory=async_sessionmaker(migrated_engine, expire_on_commit=False),
        clock=FixedClock(),
        id_factory=lambda: LOG_ID,
    )
    service = DefaultScopeClassifierService(
        classifier=CompetitorClassifier(),
        session_context=FixedContext(),
        scope_log=adapter,
    )

    decision = await service.classify_with_guidance(
        user_message="So sánh VinFast với Tesla", canonical=build_canonical_text("So sánh VinFast với Tesla")
    )

    async with migrated_engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT id, session_id, utterance, classification, reason, created_at "
                        "FROM out_of_scope_log WHERE id = :id"
                    ),
                    {"id": LOG_ID},
                )
            )
            .mappings()
            .one()
        )
    assert row["session_id"] == SESSION_ID
    assert row["utterance"] == "So sánh VinFast với Tesla"
    assert row["classification"] == ScopeLabel.OUT_OF_SCOPE.value
    assert row["reason"] == decision.limitation
    assert row["created_at"] == NOW
