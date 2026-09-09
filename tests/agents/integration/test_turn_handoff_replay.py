"""T12: `TurnHandoffService` là điểm DUY NHẤT ghi một lần chuyển người.

Một lượt chuyển người — chốt trước LLM (xin gặp người, sự cố nguy hiểm) hay
guardrail cạn lượt thử — phải tạo ĐÚNG MỘT run + MỘT mục hàng đợi duyệt + MỘT
outcome, trong một transaction. Gửi lại cùng `client_turn_id` (khách bấm gửi
lại / client retry mạng) phải trả đúng `review_id` cũ và KHÔNG được tạo mục
thứ hai — nếu không, tư vấn viên nhìn thấy hai việc cần làm cho đúng một câu
khách, và replay không còn là replay.

Câu khách đọc luôn là hằng `HANDOFF_MESSAGE` — không bao giờ mang
`advisor_content` (bản nháp/nội dung nội bộ chưa kiểm chứng) — kể cả trên
đường phát lại (outcome đã chốt đọc lại từ DB), khác hẳn nội dung ghi vào
`review_queue` cho tư vấn viên.

Test này dùng repository thật (không fake) trên DB tạm của
`tests/agents/integration/conftest.py`, để khẳng định ở tầng lưu trữ thật chứ
không chỉ ở tầng unit test với double (xem thêm
`tests/agents/unit/services/test_turn_handoff.py`).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.values import HitlReason
from src.agents.models import AgentRunRow, ConversationTurnOutcomeRow, ReviewQueueRow
from src.agents.services.turn_handoff import HANDOFF_MESSAGE, TurnHandoffService


def _unit_of_work(engine: AsyncEngine) -> AgentUnitOfWork:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=SystemClock()),
    )


async def _ensure_session(unit_of_work: AgentUnitOfWork, session_id: str, customer_id: str) -> None:
    async with unit_of_work.transaction() as transaction:
        await transaction.sessions.ensure_session(session_id, customer_id, None)


async def _row_counts(engine: AsyncEngine) -> tuple[int, int, int]:
    async with engine.connect() as connection:
        runs = await connection.scalar(select(func.count()).select_from(AgentRunRow))
        reviews = await connection.scalar(select(func.count()).select_from(ReviewQueueRow))
        outcomes = await connection.scalar(select(func.count()).select_from(ConversationTurnOutcomeRow))
    return runs, reviews, outcomes


@pytest.mark.asyncio
async def test_handoff_writes_exactly_one_run_one_review_and_one_outcome(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    unit_of_work = _unit_of_work(migrated_engine)
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _ensure_session(unit_of_work, session_id, customer_id)
    service = TurnHandoffService(unit_of_work)

    result = await service.handoff(
        session_id=session_id,
        customer_id=customer_id,
        client_turn_id=uuid4(),
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp tư vấn viên",
        advisor_content="NOI DUNG NOI BO CHUA KIEM CHUNG - khong duoc ra khach",
    )

    assert result.answer == HANDOFF_MESSAGE
    assert "NOI DUNG NOI BO" not in result.answer
    assert await _row_counts(migrated_engine) == (1, 1, 1)


@pytest.mark.asyncio
async def test_resending_the_same_client_turn_id_does_not_create_a_second_review_item(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """PRD: một lượt chuyển người tạo đúng một mục duyệt; gửi lại không tạo mục thứ hai."""

    unit_of_work = _unit_of_work(migrated_engine)
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _ensure_session(unit_of_work, session_id, customer_id)
    client_turn_id = uuid4()
    service = TurnHandoffService(unit_of_work)
    kwargs = dict(
        session_id=session_id,
        customer_id=customer_id,
        client_turn_id=client_turn_id,
        reason=HitlReason.ROADSIDE_ASSISTANCE,
        customer_message="xe em đang bốc khói trên cao tốc",
        advisor_content="ROADSIDE_ASSISTANCE | xe em đang bốc khói trên cao tốc",
    )

    first = await service.handoff(**kwargs)
    second = await service.handoff(**kwargs)

    assert first.replayed is False
    assert second.replayed is True
    assert second.review_id == first.review_id
    assert second.answer == HANDOFF_MESSAGE
    assert await _row_counts(migrated_engine) == (1, 1, 1)


@pytest.mark.asyncio
async def test_replayed_answer_is_read_back_from_the_persisted_outcome_not_recomputed(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Phát lại đọc `answer` đã chốt trong `conversation_turn_outcomes`, không tính lại."""

    unit_of_work = _unit_of_work(migrated_engine)
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _ensure_session(unit_of_work, session_id, customer_id)
    client_turn_id = uuid4()
    service = TurnHandoffService(unit_of_work)
    kwargs = dict(
        session_id=session_id,
        customer_id=customer_id,
        client_turn_id=client_turn_id,
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp người thật",
        advisor_content="CUSTOMER_REQUESTED_HUMAN | cho tôi gặp người thật",
    )
    await service.handoff(**kwargs)

    async with migrated_engine.connect() as connection:
        outcome_row = (await connection.execute(select(ConversationTurnOutcomeRow))).mappings().one()
    assert outcome_row["answer"] == HANDOFF_MESSAGE

    replay = await service.handoff(**kwargs)

    assert replay.answer == HANDOFF_MESSAGE
    assert "cho tôi gặp người thật" not in replay.answer


@pytest.mark.asyncio
async def test_the_review_queue_row_carries_advisor_content_never_the_fixed_customer_message(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Hàng đợi tư vấn viên đọc `advisor_content` nguyên văn; khách chỉ nhận HANDOFF_MESSAGE."""

    unit_of_work = _unit_of_work(migrated_engine)
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _ensure_session(unit_of_work, session_id, customer_id)
    service = TurnHandoffService(unit_of_work)

    await service.handoff(
        session_id=session_id,
        customer_id=customer_id,
        client_turn_id=uuid4(),
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp tư vấn viên",
        advisor_content="CUSTOMER_REQUESTED_HUMAN | cho tôi gặp tư vấn viên",
    )

    async with migrated_engine.connect() as connection:
        review_row = (await connection.execute(select(ReviewQueueRow))).mappings().one()

    assert review_row["content"] == "CUSTOMER_REQUESTED_HUMAN | cho tôi gặp tư vấn viên"
    assert review_row["status"] == "PENDING"
    assert HANDOFF_MESSAGE not in review_row["content"]


@pytest.mark.asyncio
async def test_a_turn_without_a_client_key_still_writes_one_run_review_and_no_outcome(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Không có khoá khử trùng lặp (`client_turn_id=None`) vẫn ghi run+review, không outcome."""

    unit_of_work = _unit_of_work(migrated_engine)
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _ensure_session(unit_of_work, session_id, customer_id)
    service = TurnHandoffService(unit_of_work)

    result = await service.handoff(
        session_id=session_id,
        customer_id=customer_id,
        client_turn_id=None,
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp tư vấn viên",
        advisor_content="noi dung noi bo",
    )

    assert result.answer == HANDOFF_MESSAGE
    runs, reviews, outcomes = await _row_counts(migrated_engine)
    assert (runs, reviews) == (1, 1)
    assert outcomes == 0
