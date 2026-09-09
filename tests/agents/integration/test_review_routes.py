"""T11 — API review mở rộng: hồ sơ trong GET, /resolve additive, list `/agent/reviews`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.review_routes import review_operations, reviews_router, router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import ReviewOperations
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)
DRAFT = "Xe dien gia 1.200.000.000 dong"

SNAPSHOT = {
    "needs": ["ngan sach 1,2 ty"],
    "considered_vehicles": ["VF 8"],
    "bottlenecks": [{"bottleneck": "PRICE", "verbatim_quote": "gia qua cao"}],
    "matched_promotions": [{"promotion_code": "FIN-01", "promotion_type": "FINANCING"}],
    "verified_number_tokens": ["1200000000"],
    "offer_state": "BOTTLENECK_OFFER_AVAILABLE",
    "unmet_demand_flag": False,
    "unmet_bottleneck": None,
    "color_preference": None,
}

POLICIES = [
    {"promotion_type": "FINANCING", "financing_months_min": 6, "financing_months_max": 36},
    {"promotion_type": "FIXED_DISCOUNT", "adjust_min_vnd": 0, "adjust_max_vnd": 10_000_000},
]


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class FakeOfferPolicy:
    """Port biên độ — trả `None` khi hợp lệ, chuỗi lý do khi vi phạm."""

    def __init__(self) -> None:
        self.adjustment_error: str | None = None
        self.promotion_error: str | None = None

    async def validate_adjustment(self, *, adjustment: dict) -> str | None:
        return self.adjustment_error

    async def validate_promotion_active(self, *, promotion_code: str, at: datetime) -> str | None:
        return self.promotion_error

    async def list_policies(self) -> list[dict]:
        return list(POLICIES)


class FakeAdjustmentLog:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


async def _seed_review(
    engine: AsyncEngine,
    *,
    status: str = "PENDING",
    content: str = DRAFT,
    snapshot: dict | None = None,
    created_at: datetime = NOW,
) -> UUID:
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
                status=status,
                created_at=created_at,
                updated_at=created_at,
                profile_snapshot=snapshot,
            )
        )
    return review_id


async def _read_row(engine: AsyncEngine, review_id: UUID) -> ReviewQueueRow:
    async with engine.connect() as connection:
        return (await connection.execute(select(ReviewQueueRow).where(ReviewQueueRow.review_id == review_id))).one()


def _build_app(
    migrated_engine: AsyncEngine,
    *,
    policy: FakeOfferPolicy | None = None,
    log: FakeAdjustmentLog | None = None,
    identity: StaffIdentity | None = None,
    authenticated: bool = True,
) -> FastAPI:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock()),
    )
    application = FastAPI()
    application.include_router(router)
    application.include_router(reviews_router)
    application.dependency_overrides[review_operations] = lambda: ReviewOperations(
        unit_of_work=unit_of_work,
        offer_policy=policy,
        offer_adjustment_log=log,
    )
    if authenticated:
        application.dependency_overrides[current_staff] = lambda: (
            identity or StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)
        )
    return application


@pytest.fixture
def policy() -> FakeOfferPolicy:
    return FakeOfferPolicy()


@pytest.fixture
def adjustment_log() -> FakeAdjustmentLog:
    return FakeAdjustmentLog()


@pytest.fixture
def app(
    migrated_engine: AsyncEngine,
    clean_agent_database: None,
    policy: FakeOfferPolicy,
    adjustment_log: FakeAdjustmentLog,
) -> FastAPI:
    return _build_app(migrated_engine, policy=policy, log=adjustment_log)


async def _call(app: FastAPI, method: str, path: str, **kwargs: object) -> tuple[int, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.request(method, path, **kwargs)  # type: ignore[arg-type]
    body = response.json() if response.content else None
    return response.status_code, body


# --- QA happy ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_returns_snapshot_offer_state_matches_and_policies(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    code, body = await _call(app, "GET", f"/agent/review/{review_id}")

    assert code == 200
    assert body["profile_snapshot"]["offer_state"] == "BOTTLENECK_OFFER_AVAILABLE"
    assert body["offer_state"] == "BOTTLENECK_OFFER_AVAILABLE"
    assert body["matched_promotions"] == SNAPSHOT["matched_promotions"]
    assert [p["promotion_type"] for p in body["adjustment_policies"]] == [
        "FINANCING",
        "FIXED_DISCOUNT",
    ]


@pytest.mark.asyncio
async def test_detail_sets_first_viewed_at_once(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    await _call(app, "GET", f"/agent/review/{review_id}")
    first = (await _read_row(migrated_engine, review_id)).first_viewed_at
    assert first is not None

    await _call(app, "GET", f"/agent/review/{review_id}")
    assert (await _read_row(migrated_engine, review_id)).first_viewed_at == first


@pytest.mark.asyncio
async def test_resolve_with_offer_in_bounds_is_approved(
    app: FastAPI, migrated_engine: AsyncEngine, adjustment_log: FakeAdjustmentLog
) -> None:
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    code, _ = await _call(
        app,
        "POST",
        f"/agent/review/{review_id}/resolve",
        json={
            "status": "APPROVED",
            "offer_adjustment": {
                "promotion_code": "FIN-01",
                "promotion_type": "FINANCING",
                "adjustment_type": "MONTHS",
                "new_value": "24",
                "months": 24,
            },
        },
    )

    assert code == 200
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "APPROVED"
    assert len(adjustment_log.records) == 1


@pytest.mark.asyncio
async def test_resolve_without_offer_is_approved(
    app: FastAPI, migrated_engine: AsyncEngine, adjustment_log: FakeAdjustmentLog
) -> None:
    """D12 — advisor được duyệt mà không cấp ưu đãi."""
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    code, _ = await _call(app, "POST", f"/agent/review/{review_id}/resolve", json={"status": "APPROVED"})

    assert code == 200
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "APPROVED"
    # Duyệt nguyên trạng không tính là "bỏ qua đề xuất" (T9 `_should_mark_ignored`).
    assert row.offer_suggestion_ignored is False
    assert adjustment_log.records == []


@pytest.mark.asyncio
async def test_resolve_reject_with_handoff_sets_flag(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    code, _ = await _call(
        app,
        "POST",
        f"/agent/review/{review_id}/resolve",
        json={"status": "REJECTED", "handoff_requested": True},
    )

    assert code == 200
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "REJECTED"
    assert row.handoff_requested is True


@pytest.mark.asyncio
async def test_reviews_list_returns_queue_entries(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    code, body = await _call(app, "GET", "/agent/reviews")

    assert code == 200
    assert [UUID(row["review_id"]) for row in body] == [review_id]
    entry = body[0]
    assert entry["offer_state"] == "BOTTLENECK_OFFER_AVAILABLE"
    assert entry["profile_snapshot"]["offer_state"] == "BOTTLENECK_OFFER_AVAILABLE"
    assert entry["handoff_requested"] is False
    assert entry["offer_suggestion_ignored"] is False
    assert "age_minutes" in entry


@pytest.mark.asyncio
async def test_reviews_list_filters_by_status(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    pending_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)
    rejected_id = await _seed_review(migrated_engine, status="REJECTED")

    code, pending = await _call(app, "GET", "/agent/reviews?status=pending")
    assert code == 200
    assert [UUID(row["review_id"]) for row in pending] == [pending_id]

    code, rejected = await _call(app, "GET", "/agent/reviews?status=rejected")
    assert code == 200
    assert [UUID(row["review_id"]) for row in rejected] == [rejected_id]


# --- QA failure -------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_out_of_bounds_is_422(
    app: FastAPI, migrated_engine: AsyncEngine, policy: FakeOfferPolicy
) -> None:
    policy.adjustment_error = "months 60 > max 36"
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    code, body = await _call(
        app,
        "POST",
        f"/agent/review/{review_id}/resolve",
        json={
            "status": "APPROVED",
            "offer_adjustment": {"promotion_type": "FINANCING", "months": 60},
        },
    )

    assert code == 422
    assert body["detail"] == "adjustment_out_of_bounds"
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "PENDING"


@pytest.mark.asyncio
async def test_resolve_expired_promotion_is_409(
    app: FastAPI, migrated_engine: AsyncEngine, policy: FakeOfferPolicy
) -> None:
    policy.promotion_error = "promotion 'FIN-01' expired"
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    code, body = await _call(
        app,
        "POST",
        f"/agent/review/{review_id}/resolve",
        json={
            "status": "APPROVED",
            "offer_adjustment": {"promotion_code": "FIN-01", "promotion_type": "FINANCING"},
        },
    )

    assert code == 409
    assert body["detail"] == "promotion_expired"


@pytest.mark.asyncio
async def test_resolve_unknown_review_is_404(app: FastAPI) -> None:
    code, _ = await _call(app, "POST", f"/agent/review/{uuid4()}/resolve", json={"status": "APPROVED"})
    assert code == 404


@pytest.mark.asyncio
async def test_customer_identity_is_forbidden(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    application = _build_app(
        migrated_engine,
        policy=FakeOfferPolicy(),
        log=FakeAdjustmentLog(),
        identity=StaffIdentity(staff_id="customer-1", role=Role.CUSTOMER),
    )
    review_id = await _seed_review(migrated_engine, snapshot=SNAPSHOT)

    detail_code, _ = await _call(application, "GET", f"/agent/review/{review_id}")
    list_code, _ = await _call(application, "GET", "/agent/reviews")
    resolve_code, _ = await _call(
        application, "POST", f"/agent/review/{review_id}/resolve", json={"status": "APPROVED"}
    )

    assert (detail_code, list_code, resolve_code) == (403, 403, 403)


@pytest.mark.asyncio
async def test_missing_staff_auth_is_401(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    application = _build_app(migrated_engine, policy=FakeOfferPolicy(), authenticated=False)

    code, _ = await _call(application, "GET", "/agent/reviews")

    assert code == 401


@pytest.mark.asyncio
async def test_reviews_list_invalid_status_is_422(app: FastAPI) -> None:
    code, _ = await _call(app, "GET", "/agent/reviews?status=invalid")
    assert code == 422


@pytest.mark.asyncio
async def test_reviews_list_limit_zero_is_400(app: FastAPI) -> None:
    code, _ = await _call(app, "GET", "/agent/reviews?limit=0")
    assert code == 400
