"""Short-lived SQLAlchemy source for sales opportunity projections."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.bottleneck_signal_repository import (
    SqlAlchemyBottleneckSignalRepository,
)
from src.agents.domain.bottleneck_signal import OpportunitySignal
from src.agents.ports import ClockPort


class SalesOpportunityDataSource:
    """Run each read through short-lived database session."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: ClockPort,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def list_opportunities(self, since: datetime, limit: int) -> tuple[OpportunitySignal, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyBottleneckSignalRepository(session, self._clock).list_opportunities(since, limit)

    async def load_opportunity_slots(self, session_ids: tuple[UUID, ...]) -> dict[UUID, dict[str, str | Decimal]]:
        async with self._session_factory() as session:
            return await SqlAlchemyBottleneckSignalRepository(session, self._clock).load_opportunity_slots(session_ids)
