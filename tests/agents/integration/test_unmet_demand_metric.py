"""T21 (D10): SQL đếm unmet_demand_flag=true trên review_queue, NULL-safe.

Tạo 4 review: (1) không nút thắt, (2) có nút thắt + có ưu đãi, (3) có nút
thắt + không ưu đãi (unmet_demand_flag=true), (4) profile_snapshot=NULL
(hàng cũ pre-migration). SQL `scripts/sql/count_unmet_demand.sql` chỉ đếm
case 3, không crash trên NULL.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.repositories import SqlAlchemyReviewQueueRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.domain.customer_profile import Bottleneck, BottleneckEvidence, OfferState, ProfileSnapshot
from src.agents.models import ReviewQueueRow

SQL_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "sql" / "count_unmet_demand.sql"


async def _enqueue(repository: SqlAlchemyReviewQueueRepository, run_id, session_id: UUID, snapshot):
    return await repository.enqueue(run_id, session_id, "noi dung du thao", snapshot=snapshot)


async def _new_run(agent_session, clock, session_id: str, customer_id: str) -> UUID:
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    return await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)


@pytest.mark.asyncio
async def test_sql_script_counts_only_unmet_demand_and_is_null_safe(agent_session):
    clock = SystemClock()
    repository = SqlAlchemyReviewQueueRepository(agent_session, clock)

    # Case 1: không nút thắt -> unmet_demand_flag=False
    session_id_1, customer_id_1 = str(uuid4()), f"customer-{uuid4()}"
    run_id_1 = await _new_run(agent_session, clock, session_id_1, customer_id_1)
    snapshot_1 = ProfileSnapshot(offer_state=OfferState.NONE_BOTTLENECK)
    await _enqueue(repository, run_id_1, UUID(session_id_1), snapshot_1)

    # Case 2: có nút thắt + có ưu đãi khớp -> unmet_demand_flag=False
    session_id_2, customer_id_2 = str(uuid4()), f"customer-{uuid4()}"
    run_id_2 = await _new_run(agent_session, clock, session_id_2, customer_id_2)
    snapshot_2 = ProfileSnapshot(
        offer_state=OfferState.BOTTLENECK_OFFER_AVAILABLE,
        bottlenecks=[BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="gia hoi cao")],
        matched_promotions=[{"promotion_id": "promo-1"}],
    )
    await _enqueue(repository, run_id_2, UUID(session_id_2), snapshot_2)

    # Case 3: có nút thắt + không ưu đãi khớp -> unmet_demand_flag=True, unmet_bottleneck=PRICE
    session_id_3, customer_id_3 = str(uuid4()), f"customer-{uuid4()}"
    run_id_3 = await _new_run(agent_session, clock, session_id_3, customer_id_3)
    snapshot_3 = ProfileSnapshot(
        offer_state=OfferState.BOTTLENECK_NO_OFFER,
        bottlenecks=[BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="gia hoi cao")],
        unmet_demand_flag=True,
        unmet_bottleneck="PRICE",
    )
    await _enqueue(repository, run_id_3, UUID(session_id_3), snapshot_3)

    # Case 4: profile_snapshot=NULL (hàng cũ pre-migration) -> không đếm, không crash
    session_id_4, customer_id_4 = str(uuid4()), f"customer-{uuid4()}"
    run_id_4 = await _new_run(agent_session, clock, session_id_4, customer_id_4)
    now = clock.now()
    agent_session.add(
        ReviewQueueRow(
            review_id=uuid4(),
            session_id=UUID(session_id_4),
            run_id=run_id_4,
            content="hang cu pre-migration",
            created_at=now,
            updated_at=now,
            profile_snapshot=None,
        )
    )
    await agent_session.flush()

    sql = SQL_SCRIPT_PATH.read_text(encoding="utf-8")
    result = (await agent_session.execute(text(sql))).all()

    assert result == [(1, "PRICE")]


@pytest.mark.asyncio
async def test_none_bottleneck_and_offer_available_are_never_flagged(agent_session):
    clock = SystemClock()
    repository = SqlAlchemyReviewQueueRepository(agent_session, clock)

    session_id_1, customer_id_1 = str(uuid4()), f"customer-{uuid4()}"
    run_id_1 = await _new_run(agent_session, clock, session_id_1, customer_id_1)
    snapshot_1 = ProfileSnapshot(offer_state=OfferState.NONE_BOTTLENECK)
    review_id_1 = await _enqueue(repository, run_id_1, UUID(session_id_1), snapshot_1)

    session_id_2, customer_id_2 = str(uuid4()), f"customer-{uuid4()}"
    run_id_2 = await _new_run(agent_session, clock, session_id_2, customer_id_2)
    snapshot_2 = ProfileSnapshot(
        offer_state=OfferState.BOTTLENECK_OFFER_AVAILABLE,
        bottlenecks=[BottleneckEvidence(bottleneck=Bottleneck.RANGE, verbatim_quote="quang duong ngan")],
        matched_promotions=[{"promotion_id": "promo-2"}],
    )
    review_id_2 = await _enqueue(repository, run_id_2, UUID(session_id_2), snapshot_2)

    item_1 = await repository.find(review_id_1)
    item_2 = await repository.find(review_id_2)

    assert item_1.profile_snapshot["unmet_demand_flag"] is False
    assert item_2.profile_snapshot["unmet_demand_flag"] is False

    sql = SQL_SCRIPT_PATH.read_text(encoding="utf-8")
    result = (await agent_session.execute(text(sql))).all()
    assert result == []
