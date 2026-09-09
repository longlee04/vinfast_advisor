"""ScoreNode doc slot tu DB trong CUNG luot graph.ainvoke (xem src/agents/chain.py).

`SlotExtractionServiceImpl.extract` phai ghi `conversation_slots` NGAY khi trich
xuat xong, khong doi den `_save_slots` cuoi `run_turn` — vi luc do ScoreNode da
doc xong va chi thay slot cua luot TRUOC. Test nay chung minh: sau khi `extract`
hoan tat, slot da COMMIT that su xuong DB, doc lai qua mot transaction/session
KHAC voi transaction dung de ghi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.conversation_repository import (
    SqlAlchemyPendingFeatureMentionRepository,
    SqlAlchemySessionRepository,
)
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.values import SlotName, VehicleType
from src.agents.ports import ClockPort, PendingFeatureMentionPort, SessionRepository
from src.agents.services.conversation import ConversationServiceImpl
from src.agents.services.slot_extraction import SlotExtractionServiceImpl

NOW = datetime(2026, 8, 11, tzinfo=UTC)
SESSION_ID = "20000000-0000-0000-0000-000000000001"
CUSTOMER_ID = "customer-1"


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return NOW


class FakeLLM:
    """Tra ve payload co san — khong goi LLM that trong test tich hop nay."""

    def __init__(self, payload: LLMExtractionPayload) -> None:
        self._payload = payload

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
        return self._payload

    async def synthesize(self, *, prompt: str) -> str:
        return prompt


@dataclass(frozen=True, slots=True)
class ConversationTransaction:
    """Cung hinh voi `ConversationTransaction` trong `composition.py` (sessions + pending_mentions)."""

    sessions: SessionRepository
    pending_mentions: PendingFeatureMentionPort


@pytest_asyncio.fixture
async def session_factory(migrated_engine: AsyncEngine, clean_agent_database: None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(migrated_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def slot_extraction_service(
    session_factory: async_sessionmaker[AsyncSession],
) -> SlotExtractionServiceImpl:
    clock = FixedClock()
    unit_of_work = AgentUnitOfWork(
        session_factory,
        transaction_factory=lambda session: ConversationTransaction(
            sessions=SqlAlchemySessionRepository(session, clock),
            pending_mentions=SqlAlchemyPendingFeatureMentionRepository(session, clock),
        ),
    )
    payload = LLMExtractionPayload(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd="1 ty 2",
        passenger_count=5,
        required_range_km=300,
        home_charging=True,
    )
    return SlotExtractionServiceImpl(FakeLLM(payload), unit_of_work)


async def _load_slots_from_a_fresh_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[SlotName, object]:
    """Doc lai qua mot `AgentUnitOfWork` MOI — khong dung transaction dung de ghi."""

    clock = FixedClock()
    reader_unit_of_work = AgentUnitOfWork(
        session_factory,
        transaction_factory=lambda session: ConversationTransaction(
            sessions=SqlAlchemySessionRepository(session, clock),
            pending_mentions=SqlAlchemyPendingFeatureMentionRepository(session, clock),
        ),
    )
    reader = ConversationServiceImpl(reader_unit_of_work)
    return await reader.load_slots(SESSION_ID, CUSTOMER_ID)


@pytest.mark.asyncio
async def test_extract_commits_slots_before_returning(
    slot_extraction_service: SlotExtractionServiceImpl,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await slot_extraction_service.extract(
        session_id=SESSION_ID,
        customer_id=CUSTOMER_ID,
        vehicle_type="CAR",
        user_message="toi can xe 5 cho, ngan sach 1 ty 2, quang duong 300km, co sac tai nha",
    )

    persisted = await _load_slots_from_a_fresh_session(session_factory)

    assert persisted == {
        SlotName.VEHICLE_TYPE: "CAR",
        SlotName.BUDGET_MAX_VND: 1_200_000_000,
        SlotName.PASSENGER_COUNT: 5,
        SlotName.REQUIRED_RANGE_KM: 300,
        SlotName.HOME_CHARGING: True,
    }
