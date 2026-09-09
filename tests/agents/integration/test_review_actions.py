"""A7-3 acceptance tests — approve / edit / reject, and the 409 wall before delivery."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.review_routes import review_operations, router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import (
    AgentRunRow,
    ConversationMessageRow,
    ConversationSessionRow,
    ReviewQueueRow,
    RunSnapshotRow,
)
from src.agents.services.operations.review import ReviewOperations
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
DRAFT = "VF 8 gia 1.200.000.000 dong, pin thue 1.900.000 dong moi thang"

# Mọi cửa đưa nội dung ra ngoài đều phải qua đây. Thêm cửa mới = thêm một dòng,
# không viết lại test — đó là cách "không đường nào bypass" đứng vững về sau.
DELIVERY_ENDPOINTS = [("POST", "/agent/review/{review_id}/deliver")]


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


async def _seed_review(engine: AsyncEngine, *, status: str = "PENDING", content: str = DRAFT) -> tuple[UUID, UUID]:
    """A run already in the queue — stands in for A6-1 until Ngọc's guardrail lands (Ráp 3)."""
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
            insert(RunSnapshotRow).values(
                snapshot_id=uuid4(),
                run_id=run_id,
                captured_at=NOW,
                payload={"promoted_price_vnd": "1200000000"},
                created_at=NOW,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=session_id,
                run_id=run_id,
                content=content,
                status=status,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return review_id, run_id


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock(NOW)),
    )
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[review_operations] = lambda: ReviewOperations(unit_of_work=unit_of_work)
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)
    return application


async def _call(app: FastAPI, method: str, path: str, **kwargs: object) -> tuple[int, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.request(method, path, **kwargs)  # type: ignore[arg-type]
    body = response.json() if response.content else None
    return response.status_code, body


async def _read_row(engine: AsyncEngine, review_id: UUID) -> ReviewQueueRow:
    async with engine.connect() as connection:
        return (await connection.execute(select(ReviewQueueRow).where(ReviewQueueRow.review_id == review_id))).one()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path_template", DELIVERY_ENDPOINTS)
@pytest.mark.parametrize("status", ["PENDING", "REJECTED"])
async def test_delivering_a_run_that_is_not_approved_or_edited_returns_409(
    app: FastAPI, migrated_engine: AsyncEngine, method: str, path_template: str, status: str
) -> None:
    # Given
    review_id, _ = await _seed_review(migrated_engine, status=status)

    # When
    status_code, _body = await _call(app, method, path_template.format(review_id=review_id))

    # Then
    assert status_code == 409


@pytest.mark.asyncio
async def test_approving_records_the_advisor_and_the_processing_time(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given
    review_id, _ = await _seed_review(migrated_engine)

    # When
    status_code, _body = await _call(app, "POST", f"/agent/review/{review_id}/approve", json={})

    # Then
    assert status_code == 200
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "APPROVED"
    assert row.advisor_id == "advisor-a"
    assert row.processed_at is not None


@pytest.mark.asyncio
async def test_editing_then_approving_records_the_advisor_and_the_processing_time(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given — same numbers, different wording
    review_id, _ = await _seed_review(migrated_engine)
    edited = f"{DRAFT}. Anh chi tham khao them nhe."

    # When
    status_code, _body = await _call(app, "POST", f"/agent/review/{review_id}/approve", json={"edited_content": edited})

    # Then
    assert status_code == 200
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "EDITED"
    assert row.advisor_id == "advisor-a"
    assert row.processed_at is not None


@pytest.mark.asyncio
async def test_rejecting_records_the_advisor_and_the_processing_time(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given
    review_id, _ = await _seed_review(migrated_engine)

    # When
    status_code, _body = await _call(app, "POST", f"/agent/review/{review_id}/reject", json={})

    # Then
    assert status_code == 200
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "REJECTED"
    assert row.advisor_id == "advisor-a"
    assert row.processed_at is not None


@pytest.mark.asyncio
async def test_an_edit_that_changes_a_number_is_rejected(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — the advisor edits the price instead of the wording
    review_id, _ = await _seed_review(migrated_engine)
    tampered = DRAFT.replace("1.200.000.000", "1.100.000.000")

    # When
    status_code, _body = await _call(
        app, "POST", f"/agent/review/{review_id}/approve", json={"edited_content": tampered}
    )

    # Then
    assert status_code == 422
    row = await _read_row(migrated_engine, review_id)
    assert row.status == "PENDING"
    assert row.processed_at is None


@pytest.mark.asyncio
async def test_approved_content_does_not_change_when_the_source_data_changes(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given — approved, then the snapshot behind it is overwritten
    review_id, run_id = await _seed_review(migrated_engine)
    await _call(app, "POST", f"/agent/review/{review_id}/approve", json={})
    _, before = await _call(app, "POST", f"/agent/review/{review_id}/deliver")

    async with migrated_engine.begin() as connection:
        await connection.execute(
            update(RunSnapshotRow)
            .where(RunSnapshotRow.run_id == run_id)
            .values(payload={"promoted_price_vnd": "999000000"})
        )

    # When
    _, after = await _call(app, "POST", f"/agent/review/{review_id}/deliver")

    # Then
    assert after == before
    assert isinstance(after, dict)
    assert after["content"] == DRAFT


@pytest.mark.asyncio
async def test_delivering_an_approved_run_returns_the_approved_content(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given
    review_id, _ = await _seed_review(migrated_engine)
    await _call(app, "POST", f"/agent/review/{review_id}/approve", json={})

    # When
    status_code, body = await _call(app, "POST", f"/agent/review/{review_id}/deliver")
    await _call(app, "POST", f"/agent/review/{review_id}/deliver")

    # Then
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["content"] == DRAFT
    async with migrated_engine.connect() as connection:
        messages = (
            await connection.execute(
                select(ConversationMessageRow.role, ConversationMessageRow.content).where(
                    ConversationMessageRow.review_id == review_id
                )
            )
        ).all()
    assert [(message.role, message.content) for message in messages] == [("ASSISTANT", DRAFT)]


@pytest.mark.asyncio
async def test_acting_on_an_unknown_review_is_rejected(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: nothing seeded for this identifier
    unknown = uuid4()

    # When
    status_code, _body = await _call(app, "POST", f"/agent/review/{unknown}/approve", json={})

    # Then
    assert status_code == 404
