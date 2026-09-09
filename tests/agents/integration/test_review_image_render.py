"""Task 5: render comparison images only when review data is opened."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.adapters.vehicle_image import MinioVehicleImageSource
from src.agents.contracts import CandidateInput
from src.agents.domain.comparison import ComparisonTable
from src.agents.domain.values import VehicleType
from src.agents.services.operations import review as review_module
from src.agents.services.operations.review import ReviewItem, ReviewOperations


class _FakeSession:
    def __init__(self, object_key: str | None) -> None:
        self.object_key = object_key
        self.closed = False

    async def scalar(self, statement: object) -> str | None:
        del statement
        return self.object_key

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


class _FakeSessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.calls = 0

    def __call__(self) -> _FakeSession:
        self.calls += 1
        return self.session


class _FailingSession:
    async def __aenter__(self) -> _FailingSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def scalar(self, statement: object) -> str | None:
        del statement
        raise OSError("catalog unavailable")


class _FailingSessionFactory:
    def __init__(self, *, fail_on_call: bool) -> None:
        self.fail_on_call = fail_on_call

    def __call__(self) -> _FailingSession:
        if self.fail_on_call:
            raise OSError("session unavailable")
        return _FailingSession()


class _FakeResponse:
    def read(self) -> bytes:
        return b"vehicle-image"

    def close(self) -> None:
        return None

    def release_conn(self) -> None:
        return None


class _FakeMinio:
    def get_object(self, *, bucket_name: str, object_name: str) -> _FakeResponse:
        del bucket_name, object_name
        return _FakeResponse()


@pytest.mark.asyncio
async def test_ranked_vehicle_ids_follow_rank_order(agent_session) -> None:
    clock = SystemClock()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    runs = SqlAlchemyRunRepository(agent_session, clock)
    run_id = await runs.create_run(session_id)
    first, second, unranked = uuid4(), uuid4(), uuid4()
    await runs.save_candidates(
        run_id,
        [
            CandidateInput(vehicle_id=first, layer_reached="L2"),
            CandidateInput(vehicle_id=second, layer_reached="L2"),
            CandidateInput(vehicle_id=unranked, layer_reached="L1"),
        ],
    )
    await runs.set_candidate_ranks(run_id, {second: 1, first: 2})

    assert await runs.ranked_vehicle_ids(run_id) == [second, first]


@pytest.mark.asyncio
async def test_vehicle_image_source_opens_and_closes_session_per_load() -> None:
    session = _FakeSession("vehicles/car.png")
    factory = _FakeSessionFactory(session)
    source = MinioVehicleImageSource(
        session_factory=factory,
        client=_FakeMinio(),
        bucket_name="p150",
    )

    result = await source.load(uuid4())

    assert result == b"vehicle-image"
    assert factory.calls == 1
    assert session.closed is True


@pytest.mark.asyncio
async def test_vehicle_image_source_returns_none_and_warns_when_session_creation_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = MinioVehicleImageSource(
        session_factory=_FailingSessionFactory(fail_on_call=True),
        client=_FakeMinio(),
        bucket_name="p150",
    )

    result = await source.load(uuid4())

    assert result is None
    assert "khong doc duoc anh xe" in caplog.text


@pytest.mark.asyncio
async def test_vehicle_image_source_returns_none_and_warns_when_catalog_read_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = MinioVehicleImageSource(
        session_factory=_FailingSessionFactory(fail_on_call=False),
        client=_FakeMinio(),
        bucket_name="p150",
    )

    result = await source.load(uuid4())

    assert result is None
    assert "khong doc duoc anh xe" in caplog.text


@dataclass
class _FakeQueue:
    item: ReviewItem

    async def claim(self, queue_id: UUID, advisor_id: str, lease_minutes: int) -> bool:
        del queue_id, advisor_id, lease_minutes
        return False

    async def exists(self, queue_id: UUID) -> bool:
        return queue_id == self.item.review_id

    async def find(self, review_id: UUID) -> ReviewItem | None:
        return self.item if review_id == self.item.review_id else None

    async def resolve(self, queue_id: UUID, advisor_id: str, status: str, edited_content: str | None) -> None:
        del queue_id, advisor_id, status, edited_content
        return None


@dataclass
class _FakeRuns:
    ranked_ids: list[UUID]

    async def ranked_vehicle_ids(self, run_id: UUID) -> list[UUID]:
        del run_id
        return self.ranked_ids


class _FakeTransaction:
    def __init__(self, item: ReviewItem, ranked_ids: list[UUID]) -> None:
        self.review_queue = _FakeQueue(item)
        self.runs = _FakeRuns(ranked_ids)


class _FakeUnitOfWork:
    def __init__(self, transaction: _FakeTransaction) -> None:
        self._transaction = transaction

    @asynccontextmanager
    async def transaction(self):
        yield self._transaction


class _FakeStore:
    def __init__(self, cached: bytes | None = None) -> None:
        self.cached = cached
        self.saved: list[tuple[UUID, bytes]] = []

    def load(self, run_id: UUID) -> bytes | None:
        del run_id
        return self.cached

    def save(self, run_id: UUID, image: bytes) -> None:
        self.saved.append((run_id, image))
        self.cached = image


class _FakeSource:
    def __init__(self, payloads: dict[UUID, bytes | None]) -> None:
        self.payloads = payloads
        self.calls: list[UUID] = []

    async def load(self, vehicle_id: UUID) -> bytes | None:
        self.calls.append(vehicle_id)
        return self.payloads[vehicle_id]


class _FakeRecommendation:
    async def compare(self, *, run_id: UUID, vehicle_ids: list[UUID]) -> ComparisonTable:
        return ComparisonTable(
            vehicle_type=VehicleType.CAR,
            vehicle_ids=tuple(vehicle_ids),
            rows=(),
            captured_at=None,
        )


def _review_item(run_id: UUID, review_id: UUID) -> ReviewItem:
    return ReviewItem(review_id, uuid4(), run_id, "PENDING", "draft", None)


@pytest.mark.asyncio
async def test_image_for_review_renders_late_and_caches_by_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id, review_id = uuid4(), uuid4()
    first, second = uuid4(), uuid4()
    transaction = _FakeTransaction(_review_item(run_id, review_id), [first, second])
    store = _FakeStore()
    source = _FakeSource({first: b"first", second: b"second"})
    recommendation = _FakeRecommendation()
    render_calls = 0

    def render(table: ComparisonTable, *, photos: dict[UUID, bytes]) -> bytes:
        nonlocal render_calls
        render_calls += 1
        assert table.vehicle_ids == (first, second)
        assert photos == {first: b"first", second: b"second"}
        return b"rendered"

    monkeypatch.setattr(review_module, "render_comparison_image_or_none", render)
    operations = ReviewOperations(
        _FakeUnitOfWork(transaction),
        image_store=store,
        image_source=source,
        recommendation=recommendation,
    )

    first_result = await operations.image_for_review(review_id)
    second_result = await operations.image_for_review(review_id)

    assert first_result == b"rendered"
    assert second_result == b"rendered"
    assert render_calls == 1
    assert source.calls == [first, second]
    assert store.saved == [(run_id, b"rendered")]


@pytest.mark.asyncio
async def test_image_for_review_returns_none_without_two_ranked_vehicles() -> None:
    run_id, review_id = uuid4(), uuid4()
    transaction = _FakeTransaction(_review_item(run_id, review_id), [uuid4()])
    operations = ReviewOperations(
        _FakeUnitOfWork(transaction),
        image_store=_FakeStore(),
        image_source=_FakeSource({}),
        recommendation=_FakeRecommendation(),
    )

    assert await operations.image_for_review(review_id) is None


@pytest.mark.asyncio
async def test_image_for_review_returns_none_when_optional_collaborator_missing() -> None:
    run_id, review_id = uuid4(), uuid4()
    transaction = _FakeTransaction(_review_item(run_id, review_id), [uuid4(), uuid4()])

    assert await ReviewOperations(_FakeUnitOfWork(transaction)).image_for_review(review_id) is None
