"""Tu van vien phai doc duoc ban nhap va anh so sanh truoc khi bam duyet."""

from __future__ import annotations

from base64 import b64decode
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.review_routes import review_operations
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import ReviewOperations
from src.api.router import api_router
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


async def _seed_review(engine: AsyncEngine, *, status: str, content: str) -> UUID:
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
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return review_id


def _png_bytes() -> bytes:
    """PNG that xac dinh, dung lam moc so sanh cho phan base64 cua route."""
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class _StubbedImageOperations(ReviewOperations):
    """Thay dung mat xich doc anh; phan con lai van la use case that."""

    async def image_for_review(self, review_id: UUID) -> bytes | None:
        return _png_bytes()


@pytest.fixture
def unit_of_work(migrated_engine: AsyncEngine, clean_agent_database: None) -> AgentUnitOfWork:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    return AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock()),
    )


@pytest.fixture
def app(unit_of_work: AgentUnitOfWork) -> FastAPI:
    application = FastAPI()
    application.include_router(api_router)
    application.dependency_overrides[review_operations] = lambda: ReviewOperations(unit_of_work)
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-1", role=Role.ADVISOR)
    return application


@pytest.mark.asyncio
async def test_advisor_reads_pending_draft_before_approving(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id = await _seed_review(migrated_engine, status="PENDING", content="De xuat VF 5 va VF 6")

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/review/{review_id}")

    # Then
    assert response.status_code == 200
    body = response.json()
    assert body["review_id"] == str(review_id)
    assert body["status"] == "PENDING"
    assert body["content"] == "De xuat VF 5 va VF 6"
    assert body["edited_content"] is None


@pytest.mark.asyncio
async def test_missing_review_is_reported_as_not_found(app: FastAPI, clean_agent_database: None) -> None:
    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/review/{uuid4()}")

    # Then
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_customer_role_cannot_read_a_pending_draft(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id = await _seed_review(migrated_engine, status="PENDING", content="Noi dung chua duyet")
    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="customer-1", role=Role.CUSTOMER)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/review/{review_id}")

    # Then
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_detail_returns_null_image_when_no_image_source_is_wired(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id = await _seed_review(migrated_engine, status="PENDING", content="Khong co anh")

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/review/{review_id}")

    # Then
    assert response.status_code == 200
    assert response.json()["comparison_image_base64"] is None


@pytest.mark.asyncio
async def test_detail_base64_encodes_the_rendered_comparison_image(
    app: FastAPI,
    unit_of_work: AgentUnitOfWork,
    migrated_engine: AsyncEngine,
    clean_agent_database: None,
) -> None:
    # Given
    review_id = await _seed_review(migrated_engine, status="PENDING", content="Co anh")
    app.dependency_overrides[review_operations] = lambda: _StubbedImageOperations(unit_of_work)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/review/{review_id}")

    # Then
    assert response.status_code == 200
    encoded = response.json()["comparison_image_base64"]
    assert encoded is not None
    assert b64decode(encoded) == _png_bytes()
