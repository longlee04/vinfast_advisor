"""Task 8 REST contract for customer-owned approved review deliveries."""

from base64 import b64encode
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.review_routes import review_operations
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import ReviewItem, ReviewOperations
from src.api.router import api_router

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
CUSTOMER_ID = "customer-1"
OTHER_CUSTOMER_ID = "customer-2"


class FrozenClock:
    def now(self) -> datetime:
        return NOW


async def _seed_review(
    engine: AsyncEngine,
    *,
    customer_id: str,
    status: str,
    content: str,
    edited_content: str | None = None,
    session_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    resolved_session_id = session_id or uuid4()
    review_id = uuid4()
    async with engine.begin() as connection:
        if session_id is None:
            await connection.execute(
                insert(ConversationSessionRow).values(
                    session_id=resolved_session_id,
                    customer_id=customer_id,
                    started_at=NOW,
                    last_activity_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        run_id = uuid4()
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=resolved_session_id,
                state="APPROVED",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=resolved_session_id,
                run_id=run_id,
                content=content,
                edited_content=edited_content,
                status=status,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return resolved_session_id, review_id


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock()),
    )
    application = FastAPI()
    application.include_router(api_router)
    application.dependency_overrides[get_current_customer_id] = lambda: CUSTOMER_ID
    application.dependency_overrides[review_operations] = lambda: ReviewOperations(unit_of_work)
    return application


async def _get(app: FastAPI, path: str) -> tuple[int, dict[str, object]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(path)
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_customer_deliveries_return_only_approved_or_edited_items_for_owned_session(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, approved_id = await _seed_review(
        migrated_engine, customer_id=CUSTOMER_ID, status="APPROVED", content="Approved content"
    )
    _edited_session_id, edited_id = await _seed_review(
        migrated_engine,
        customer_id=CUSTOMER_ID,
        status="EDITED",
        content="Draft content",
        edited_content="Edited content",
        session_id=session_id,
    )
    await _seed_review(
        migrated_engine, customer_id=CUSTOMER_ID, status="PENDING", content="Draft only", session_id=session_id
    )
    await _seed_review(
        migrated_engine, customer_id=CUSTOMER_ID, status="REJECTED", content="Rejected only", session_id=session_id
    )

    # When
    status_code, body = await _get(app, f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert status_code == 200
    assert {(item["review_id"], item["content"], item["comparison_image_base64"]) for item in body["items"]} == {
        (str(approved_id), "Approved content", None),
        (str(edited_id), "Edited content", None),
    }


@pytest.mark.asyncio
async def test_customer_deliveries_use_shared_deliverable_gate(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    session_id, approved_id = await _seed_review(
        migrated_engine, customer_id=CUSTOMER_ID, status="APPROVED", content="Approved content"
    )
    _edited_session_id, edited_id = await _seed_review(
        migrated_engine,
        customer_id=CUSTOMER_ID,
        status="EDITED",
        content="Draft content",
        edited_content="Edited content",
        session_id=session_id,
    )
    _pending_session_id, pending_id = await _seed_review(
        migrated_engine,
        customer_id=CUSTOMER_ID,
        status="PENDING",
        content="Pending content",
        session_id=session_id,
    )
    _rejected_session_id, rejected_id = await _seed_review(
        migrated_engine,
        customer_id=CUSTOMER_ID,
        status="REJECTED",
        content="Rejected content",
        session_id=session_id,
    )
    calls: list[UUID] = []
    original_gate = ReviewOperations.deliverable_for_customer

    async def recording_gate(operations: ReviewOperations, candidate_id: UUID) -> ReviewItem:
        calls.append(candidate_id)
        return await original_gate(operations, candidate_id)

    monkeypatch.setattr(ReviewOperations, "deliverable_for_customer", recording_gate)

    # When
    status_code, body = await _get(app, f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert status_code == 200
    assert {(item["review_id"], item["content"], item["comparison_image_base64"]) for item in body["items"]} == {
        (str(approved_id), "Approved content", None),
        (str(edited_id), "Edited content", None),
    }
    assert set(calls) == {approved_id, edited_id, pending_id, rejected_id}
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_customer_deliveries_return_edited_content_and_optional_base64_image(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, review_id = await _seed_review(
        migrated_engine,
        customer_id=CUSTOMER_ID,
        status="EDITED",
        content="Draft content",
        edited_content="Edited content",
    )

    # When
    status_code, body = await _get(app, f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert status_code == 200
    assert body["items"] == [
        {
            "review_id": str(review_id),
            "content": "Edited content",
            "status": "EDITED",
            "comparison_image_base64": None,
        }
    ]
    assert b64encode(b"image").decode("ascii") != ""


@pytest.mark.asyncio
async def test_customer_deliveries_require_authentication(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, _review_id = await _seed_review(
        migrated_engine, customer_id=CUSTOMER_ID, status="APPROVED", content="Approved content"
    )
    app.dependency_overrides[get_current_customer_id] = lambda: None

    # When
    status_code, _body = await _get(app, f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert status_code == 401


@pytest.mark.asyncio
async def test_customer_deliveries_for_other_customer_session_return_forbidden(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, _review_id = await _seed_review(
        migrated_engine, customer_id=OTHER_CUSTOMER_ID, status="APPROVED", content="Private content"
    )

    # When
    status_code, _body = await _get(app, f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert status_code == 403
