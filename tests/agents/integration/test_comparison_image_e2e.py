"""Task 9 E2E: approved comparison image reaches owning customer exactly once."""

from __future__ import annotations

from base64 import b64decode
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.customer_routes import router as customer_router
from src.agents.api.customer_routes import turn_event_broker
from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.review_routes import review_operations
from src.agents.api.review_routes import router as review_router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.domain.comparison import ComparisonTable
from src.agents.models import ReviewQueueRow, RunCandidateRow
from src.agents.services.operations.comparison_image import ComparisonImageStore
from src.agents.services.operations.review import ReviewOperations
from src.auth.domain.authorization import Role
from tests.agents.integration.test_comparison_image_delivery import NOW, FrozenClock, _seed_review
from tests.agents.integration.test_resolve_publishes_event import RecordingBroker
from tests.agents.unit.services.test_comparison_image import _table


class _FakeVehicleImageSource:
    """Return deterministic Pillow images and count source reads."""

    def __init__(self, vehicle_ids: tuple[UUID, UUID]) -> None:
        self._vehicle_ids = vehicle_ids
        self.calls: list[UUID] = []

    async def load(self, vehicle_id: UUID) -> bytes | None:
        self.calls.append(vehicle_id)
        if vehicle_id not in self._vehicle_ids:
            return None
        image = Image.new("RGB", (32, 32), "white")
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


class _FakeRecommendation:
    def __init__(self, vehicle_ids: tuple[UUID, UUID]) -> None:
        self._vehicle_ids = vehicle_ids

    async def compare(self, *, run_id: UUID, vehicle_ids: list[UUID]) -> ComparisonTable:
        del run_id
        assert vehicle_ids == list(self._vehicle_ids)
        return _table()


async def _call(app: FastAPI, method: str, path: str, **kwargs: object) -> tuple[int, dict[str, object]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.request(method, path, **kwargs)  # type: ignore[arg-type]
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_review_image_reaches_customer_after_approval(
    migrated_engine: AsyncEngine, clean_agent_database: None, tmp_path: Path
) -> None:
    # Given — pending review is tied to one run with two ranked vehicles.
    review_id, run_id = await _seed_review(migrated_engine)
    vehicle_ids = (uuid4(), uuid4())
    async with migrated_engine.begin() as connection:
        session_id = await connection.scalar(
            select(ReviewQueueRow.session_id).where(ReviewQueueRow.review_id == review_id)
        )
        assert session_id is not None
        await connection.execute(
            insert(RunCandidateRow),
            [
                {
                    "id": uuid4(),
                    "run_id": run_id,
                    "vehicle_id": vehicle_ids[0],
                    "layer_reached": "L2",
                    "rank": 1,
                    "created_at": NOW,
                },
                {
                    "id": uuid4(),
                    "run_id": run_id,
                    "vehicle_id": vehicle_ids[1],
                    "layer_reached": "L2",
                    "rank": 2,
                    "created_at": NOW,
                },
            ],
        )

    source = _FakeVehicleImageSource(vehicle_ids)
    broker = RecordingBroker(migrated_engine)
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    operations = ReviewOperations(
        AgentUnitOfWork(
            session_factory=session_factory,
            transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock(NOW)),
        ),
        image_store=ComparisonImageStore(tmp_path),
        image_source=source,
        recommendation=_FakeRecommendation(vehicle_ids),
        broker=broker,
    )
    app = FastAPI()
    app.include_router(review_router)
    app.include_router(customer_router)
    app.dependency_overrides[review_operations] = lambda: operations
    app.dependency_overrides[turn_event_broker] = lambda: broker
    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)
    app.dependency_overrides[get_current_customer_id] = lambda: "customer-1"

    # When — customer reads pending queue, then advisor approves, then customer reads twice.
    pending_status, pending_body = await _call(app, "GET", f"/agent/deliveries/{session_id}")
    assert source.calls == []
    approve_status, _approve_body = await _call(app, "POST", f"/agent/review/{review_id}/approve", json={})
    first_status, first_body = await _call(app, "GET", f"/agent/deliveries/{session_id}")
    second_status, second_body = await _call(app, "GET", f"/agent/deliveries/{session_id}")

    # Then — pending is invisible; approval emits one correct-session event; REST exposes one cached image.
    assert pending_status == 200
    assert pending_body["items"] == []
    assert approve_status == 200
    assert len(broker.events) == 1
    assert broker.events[0].session_id == session_id
    assert broker.events[0].review_id == review_id
    assert broker.events[0].kind == "approved"
    assert first_status == second_status == 200
    assert len(first_body["items"]) == len(second_body["items"]) == 1
    first_item = first_body["items"][0]
    second_item = second_body["items"][0]
    assert first_item["review_id"] == second_item["review_id"] == str(review_id)
    assert first_item["content"] == second_item["content"] == "VF 8 gia 1.200.000.000 dong"
    first_image = b64decode(first_item["comparison_image_base64"])
    second_image = b64decode(second_item["comparison_image_base64"])
    assert first_image == second_image
    assert first_image.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(first_image)) as image:
        assert image.format == "PNG"
        image.verify()
    assert source.calls == [vehicle_ids[0], vehicle_ids[1]]
