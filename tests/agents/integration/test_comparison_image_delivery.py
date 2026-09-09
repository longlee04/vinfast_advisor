"""comparison-image — ảnh chỉ ra khỏi hệ thống sau khi bản nháp được duyệt (HITL A7)."""

from base64 import b64decode
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.review_routes import review_operations, router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.comparison_image import ComparisonImageStore
from src.agents.services.operations.review import (
    ReviewItem,
    ReviewNotApprovedError,
    ReviewOperations,
)
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-for-delivery-test"


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


async def _seed_review(engine: AsyncEngine, *, status: str = "PENDING") -> tuple[UUID, UUID]:
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
                content="VF 8 gia 1.200.000.000 dong",
                status=status,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return review_id, run_id


@pytest.fixture
def store(tmp_path: Path) -> ComparisonImageStore:
    return ComparisonImageStore(tmp_path)


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None, store: ComparisonImageStore) -> FastAPI:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock(NOW)),
    )
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[review_operations] = lambda: ReviewOperations(
        unit_of_work=unit_of_work, image_store=store
    )
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)
    return application


async def _call(app: FastAPI, method: str, path: str, **kwargs: object) -> tuple[int, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.request(method, path, **kwargs)  # type: ignore[arg-type]
    return response.status_code, (response.json() if response.content else None)


class _DeliverableOperations:
    def __init__(self, item: ReviewItem) -> None:
        self._item = item
        self.image_calls = 0

    async def deliverable_for_customer(self, review_id: UUID) -> ReviewItem:
        if review_id != self._item.review_id or self._item.status not in {"APPROVED", "EDITED"}:
            raise ReviewNotApprovedError(str(review_id))
        return self._item

    async def image_for_review(self, review_id: UUID) -> bytes:
        assert review_id == self._item.review_id
        self.image_calls += 1
        return PNG_BYTES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_status", "expected_image_calls"),
    [("PENDING", 409, 0), ("REJECTED", 409, 0), ("APPROVED", 200, 1)],
)
async def test_delivery_calls_image_only_after_deliverable_status_gate(
    status: str, expected_status: int, expected_image_calls: int
) -> None:
    review_id, run_id = uuid4(), uuid4()
    operations = _DeliverableOperations(ReviewItem(review_id, uuid4(), run_id, status, "approved content", None))
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[review_operations] = lambda: operations
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)

    status_code, _body = await _call(application, "POST", f"/agent/review/{review_id}/deliver")

    assert status_code == expected_status
    assert operations.image_calls == expected_image_calls


@pytest.mark.asyncio
async def test_an_unapproved_run_does_not_release_the_comparison_image(
    app: FastAPI, migrated_engine: AsyncEngine, store: ComparisonImageStore
) -> None:
    # Given — ảnh đã sẵn sàng, nhưng bản nháp chưa ai duyệt
    review_id, run_id = await _seed_review(migrated_engine)
    store.save(run_id, PNG_BYTES)

    # When
    status_code, body = await _call(app, "POST", f"/agent/review/{review_id}/deliver")

    # Then — ảnh đi cùng cửa gửi khách, nên bị chặn đúng như phần văn bản
    assert status_code == 409
    assert body != PNG_BYTES


@pytest.mark.asyncio
async def test_an_approved_run_releases_the_comparison_image(
    app: FastAPI, migrated_engine: AsyncEngine, store: ComparisonImageStore
) -> None:
    # Given
    review_id, run_id = await _seed_review(migrated_engine)
    store.save(run_id, PNG_BYTES)
    await _call(app, "POST", f"/agent/review/{review_id}/approve", json={})

    # When
    status_code, body = await _call(app, "POST", f"/agent/review/{review_id}/deliver")

    # Then
    assert status_code == 200
    assert isinstance(body, dict)
    assert b64decode(body["comparison_image_base64"]) == PNG_BYTES


@pytest.mark.asyncio
async def test_an_approved_run_without_an_image_still_delivers_the_text(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given — test âm: không có ảnh cũng không được làm hỏng phần văn bản
    review_id, _ = await _seed_review(migrated_engine)
    await _call(app, "POST", f"/agent/review/{review_id}/approve", json={})

    # When
    status_code, body = await _call(app, "POST", f"/agent/review/{review_id}/deliver")

    # Then
    assert status_code == 200
    assert isinstance(body, dict)
    assert body["comparison_image_base64"] is None
    assert body["content"] == "VF 8 gia 1.200.000.000 dong"


@pytest.mark.asyncio
async def test_a_rejected_run_does_not_release_the_comparison_image(
    app: FastAPI, migrated_engine: AsyncEngine, store: ComparisonImageStore
) -> None:
    # Given — test âm: từ chối cũng là chưa duyệt
    review_id, run_id = await _seed_review(migrated_engine, status="REJECTED")
    store.save(run_id, PNG_BYTES)

    # When
    status_code, _body = await _call(app, "POST", f"/agent/review/{review_id}/deliver")

    # Then
    assert status_code == 409
