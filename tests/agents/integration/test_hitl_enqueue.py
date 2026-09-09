"""PRD 5.6: noi dung phai vao hang doi PENDING truoc khi toi khach."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.repositories import SqlAlchemyReviewQueueRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.models import ReviewQueueRow


@pytest.mark.asyncio
async def test_enqueue_creates_a_pending_item_for_the_run(agent_session):
    clock = SystemClock()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    run_id = await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)
    repository = SqlAlchemyReviewQueueRepository(agent_session, clock)

    review_id = await repository.enqueue(run_id, UUID(session_id), "VF 6 phu hop nhu cau cua ban.")

    row = await agent_session.scalar(select(ReviewQueueRow).where(ReviewQueueRow.review_id == review_id))
    assert row.status == "PENDING"
    assert row.run_id == run_id
    assert row.content == "VF 6 phu hop nhu cau cua ban."
    assert row.claimed_by is None


@pytest.mark.asyncio
async def test_enqueue_alone_does_not_deduplicate_across_calls(agent_session):
    """T12: `enqueue` là hàng đợi thô, đẩy gì ghi nấy - việc "đúng một mục duyệt
    cho một lượt chuyển người" là trách nhiệm của `TurnHandoffService` (khoá
    `client_turn_id` qua `outcomes.claim`), KHÔNG phải của repository này. Test
    này khoá ranh giới đó: gọi `enqueue` hai lần cho cùng một run/session tạo
    hai mục PENDING riêng, không tự gộp lại.
    """
    clock = SystemClock()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    run_id = await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)
    repository = SqlAlchemyReviewQueueRepository(agent_session, clock)

    first = await repository.enqueue(run_id, UUID(session_id), "Ban nhap lan 1")
    second = await repository.enqueue(run_id, UUID(session_id), "Ban nhap lan 2")

    assert first != second
    rows = (
        await agent_session.scalars(select(ReviewQueueRow).where(ReviewQueueRow.run_id == run_id))
    ).all()
    assert {row.status for row in rows} == {"PENDING"}
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_enqueue_of_empty_content_is_rejected(agent_session):
    clock = SystemClock()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    run_id = await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)
    repository = SqlAlchemyReviewQueueRepository(agent_session, clock)

    with pytest.raises(ValueError):
        await repository.enqueue(run_id, UUID(session_id), "   ")
