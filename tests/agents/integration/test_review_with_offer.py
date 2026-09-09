"""Integration tests for ReviewOperations.resolve_with_offer (C3)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import (
    EditedNumbersChangedError,
    OfferAdjustmentOutOfBoundsError,
    OfferPromotionExpiredError,
    ReviewOperations,
    UntracedNumberError,
)

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
DRAFT = "VF 8 gia 1.200.000.000 dong, pin thue 1.900.000 dong moi thang"


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class FakeOfferPolicy:
    def __init__(self) -> None:
        self.adjustment_error: str | None = None
        self.promotion_error: str | None = None
        self.calls: list[dict] = []

    async def validate_adjustment(self, *, adjustment: dict) -> str | None:
        self.calls.append({"op": "adjustment", "adjustment": adjustment})
        return self.adjustment_error

    async def validate_promotion_active(self, *, promotion_code: str, at: datetime) -> str | None:
        self.calls.append({"op": "promotion", "code": promotion_code})
        return self.promotion_error


class FakeAdjustmentLog:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


async def _seed_review(
    engine: AsyncEngine,
    *,
    content: str = DRAFT,
    snapshot: dict | None = None,
) -> tuple[UUID, UUID]:
    session_id = uuid4()
    run_id = uuid4()
    review_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id="customer-1",
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=session_id,
                state="PENDING_REVIEW",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=session_id,
                run_id=run_id,
                content=content,
                status="PENDING",
                created_at=NOW,
                updated_at=NOW,
                profile_snapshot=snapshot,
            )
        )
    return review_id, run_id


async def _read_row(engine: AsyncEngine, review_id: UUID) -> ReviewQueueRow:
    async with engine.connect() as connection:
        return (await connection.execute(select(ReviewQueueRow).where(ReviewQueueRow.review_id == review_id))).one()


def _make_ops(migrated_engine: AsyncEngine, policy, log) -> ReviewOperations:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock(NOW)),
    )
    return ReviewOperations(
        unit_of_work=unit_of_work,
        offer_policy=policy,
        offer_adjustment_log=log,
    )


@pytest.mark.asyncio
async def test_approve_with_offer_in_bounds_records_log(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    review_id, _ = await _seed_review(migrated_engine)
    policy = FakeOfferPolicy()
    log = FakeAdjustmentLog()
    ops = _make_ops(migrated_engine, policy, log)
    adjustment = {
        "promotion_code": "FIN-1",
        "promotion_type": "FINANCING",
        "adjustment_type": "VND",
        "new_value": "10000000",
    }

    await ops.resolve_with_offer(review_id, "advisor-a", "APPROVED", offer_adjustment=adjustment)

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "APPROVED"
    assert row.advisor_id == "advisor-a"
    assert len(log.records) == 1
    assert log.records[0]["promotion_code"] == "FIN-1"
    assert log.records[0]["source_kind"] == "CONTENT_REVIEW"
    assert log.records[0]["source_id"] == review_id
    assert log.records[0]["review_id"] == review_id


@pytest.mark.asyncio
async def test_offer_out_of_bounds_raises_and_does_not_resolve(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    review_id, _ = await _seed_review(migrated_engine)
    policy = FakeOfferPolicy()
    policy.adjustment_error = "amount above maximum"
    ops = _make_ops(migrated_engine, policy, FakeAdjustmentLog())
    adjustment = {
        "promotion_code": "FIN-1",
        "promotion_type": "FINANCING",
        "adjustment_type": "VND",
        "new_value": "999999999",
    }

    with pytest.raises(OfferAdjustmentOutOfBoundsError):
        await ops.resolve_with_offer(review_id, "advisor-a", "APPROVED", offer_adjustment=adjustment)

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "PENDING"
    assert row.processed_at is None


@pytest.mark.asyncio
async def test_expired_promotion_raises_promotion_error(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    review_id, _ = await _seed_review(migrated_engine)
    policy = FakeOfferPolicy()
    policy.promotion_error = "promotion is not ACTIVE in the current window"
    ops = _make_ops(migrated_engine, policy, FakeAdjustmentLog())
    adjustment = {
        "promotion_code": "FIN-1",
        "promotion_type": "FINANCING",
        "adjustment_type": "VND",
        "new_value": "10000000",
    }

    with pytest.raises(OfferPromotionExpiredError):
        await ops.resolve_with_offer(review_id, "advisor-a", "APPROVED", offer_adjustment=adjustment)

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "PENDING"


@pytest.mark.asyncio
async def test_approve_without_offer_no_log(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    review_id, _ = await _seed_review(migrated_engine)
    policy = FakeOfferPolicy()
    log = FakeAdjustmentLog()
    ops = _make_ops(migrated_engine, policy, log)

    await ops.resolve_with_offer(review_id, "advisor-a", "APPROVED")

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "APPROVED"
    assert row.offer_suggestion_ignored is False
    assert log.records == []


@pytest.mark.asyncio
async def test_handoff_rejected_sets_flag(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    review_id, _ = await _seed_review(migrated_engine)
    ops = _make_ops(migrated_engine, FakeOfferPolicy(), FakeAdjustmentLog())

    await ops.resolve_with_offer(review_id, "advisor-a", "REJECTED", handoff_requested=True)

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "REJECTED"
    assert row.handoff_requested is True


@pytest.mark.asyncio
async def test_guard_1a_approve_as_is_with_untraced_number_raises(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Content chứa "50%" không nằm trong verified_number_tokens của snapshot.
    content = "Xe nay duoc giam 50% le phi"
    snapshot = {"verified_number_tokens": ["1200000000", "1900000"]}
    review_id, _ = await _seed_review(migrated_engine, content=content, snapshot=snapshot)
    ops = _make_ops(migrated_engine, FakeOfferPolicy(), FakeAdjustmentLog())

    with pytest.raises(UntracedNumberError):
        await ops.resolve_with_offer(review_id, "advisor-a", "APPROVED")


@pytest.mark.asyncio
async def test_guard_1a_approve_as_is_with_verified_numbers_passes(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    content = "Xe nay gia 1200000000 dong"
    snapshot = {"verified_number_tokens": ["1200000000", "1900000"]}
    review_id, _ = await _seed_review(migrated_engine, content=content, snapshot=snapshot)
    ops = _make_ops(migrated_engine, FakeOfferPolicy(), FakeAdjustmentLog())

    await ops.resolve_with_offer(review_id, "advisor-a", "APPROVED")

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "APPROVED"


@pytest.mark.asyncio
async def test_edited_removing_untraced_number_allowed(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Fold #1: advisor xoá "50%" (không traceable) → cho phép.
    content = "Xe nay duoc giam 50% le phi, gia 1200000000"
    snapshot = {"verified_number_tokens": ["1200000000"]}
    review_id, _ = await _seed_review(migrated_engine, content=content, snapshot=snapshot)
    ops = _make_ops(migrated_engine, FakeOfferPolicy(), FakeAdjustmentLog())

    await ops.resolve_with_offer(
        review_id,
        "advisor-a",
        "APPROVED",
        edited_content="Xe nay duoc giam le phi, gia 1200000000",
    )

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "EDITED"


@pytest.mark.asyncio
async def test_edited_removing_verified_number_raises(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Fold #1: xoá số traceable (giá) → vẫn chặn.
    content = "Xe nay gia 1200000000 dong"
    snapshot = {"verified_number_tokens": ["1200000000"]}
    review_id, _ = await _seed_review(migrated_engine, content=content, snapshot=snapshot)
    ops = _make_ops(migrated_engine, FakeOfferPolicy(), FakeAdjustmentLog())

    with pytest.raises(EditedNumbersChangedError):
        await ops.resolve_with_offer(
            review_id,
            "advisor-a",
            "APPROVED",
            edited_content="Xe nay gia dong",
        )


@pytest.mark.asyncio
async def test_guard_1a_also_covers_legacy_approve_route(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Guard 1A phải chặn cả cửa `/approve` cũ, không riêng `/resolve`.

    Panel tư vấn viên duyệt nguyên trạng qua `approve()`; nếu guard chỉ nằm ở
    `resolve_with_offer` thì đúng đường đi phổ biến nhất lại không được canh.
    """

    content = "Xe nay duoc giam 50% le phi"
    snapshot = {"verified_number_tokens": ["1200000000", "1900000"]}
    review_id, _ = await _seed_review(migrated_engine, content=content, snapshot=snapshot)
    ops = _make_ops(migrated_engine, FakeOfferPolicy(), FakeAdjustmentLog())

    with pytest.raises(UntracedNumberError):
        await ops.approve(review_id, "advisor-a")


@pytest.mark.asyncio
async def test_legacy_approve_route_still_passes_verified_numbers(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    content = "Xe nay gia 1200000000 dong"
    snapshot = {"verified_number_tokens": ["1200000000", "1900000"]}
    review_id, _ = await _seed_review(migrated_engine, content=content, snapshot=snapshot)
    ops = _make_ops(migrated_engine, FakeOfferPolicy(), FakeAdjustmentLog())

    await ops.approve(review_id, "advisor-a")

    row = await _read_row(migrated_engine, review_id)
    assert row.status == "APPROVED"
