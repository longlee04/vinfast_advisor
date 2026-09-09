"""HTTP contract tests for staff bottleneck signal workflow."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api.bottleneck_signal_routes import bottleneck_signal_operations, router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.domain.bottleneck_signal import BottleneckSignal, BottleneckSignalStatus
from src.agents.domain.customer_profile import Bottleneck
from src.agents.services.operations.bottleneck_signal import (
    BottleneckSignalDetail,
    SignalOfferConflictError,
)
from src.auth.domain.authorization import Role
from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentOutOfBoundsError,
    PromotionExpiredError,
)

NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)
SIGNAL_ID = UUID("40000000-0000-0000-0000-000000000001")


def _signal() -> BottleneckSignal:
    return BottleneckSignal(
        signal_id=SIGNAL_ID,
        session_id=uuid4(),
        client_turn_id=uuid4(),
        anchor_client_turn_id=uuid4(),
        label=Bottleneck.PRICE,
        evidence_quote="Giá cao; token=[REDACTED]",
        model_name="secret-model",
        prompt_version="secret-prompt",
        status=BottleneckSignalStatus.PENDING,
        claimed_by=None,
        claimed_at=None,
        lease_expires_at=None,
        advisor_id=None,
        decided_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeOperations:
    def __init__(self) -> None:
        self.signal = _signal()
        self.list_args: tuple[BottleneckSignalStatus, int, int] | None = None
        self.offer_error: Exception | None = None
        self.offer: OfferAdjustment | None = None

    async def list_signals(
        self, signal_status: BottleneckSignalStatus, limit: int, offset: int
    ) -> tuple[BottleneckSignal, ...]:
        self.list_args = (signal_status, limit, offset)
        return (self.signal,)

    async def detail(self, signal_id: UUID) -> BottleneckSignalDetail:
        assert signal_id == SIGNAL_ID
        return BottleneckSignalDetail(
            signal=self.signal,
            matched_promotions=({"code": "PRICE-10"},),
            adjustment_policies=({"promotion_type": "DISCOUNT"},),
        )

    async def claim(self, signal_id: UUID, advisor_id: str) -> BottleneckSignal:
        assert signal_id == SIGNAL_ID
        assert advisor_id == "advisor-1"
        return self.signal

    async def verdict(self, signal_id: UUID, advisor_id: str, verdict: str) -> BottleneckSignal:
        assert signal_id == SIGNAL_ID
        assert advisor_id == "advisor-1"
        assert verdict == "CORRECT"
        return self.signal

    async def submit_offer(self, signal_id: UUID, advisor_id: str, adjustment: OfferAdjustment) -> None:
        assert signal_id == SIGNAL_ID
        assert advisor_id == "advisor-1"
        if self.offer_error is not None:
            raise self.offer_error
        self.offer = adjustment


@pytest.fixture
def operations() -> FakeOperations:
    return FakeOperations()


@pytest.fixture
def app(operations: FakeOperations) -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[bottleneck_signal_operations] = lambda: operations
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-1", role=Role.ADVISOR)
    return application


async def _request(app: FastAPI, method: str, path: str, **kwargs: object):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://agent-test") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_staff_lists_bounded_filtered_safe_signals(app: FastAPI, operations: FakeOperations) -> None:
    # Given / When
    response = await _request(app, "GET", "/agent/bottleneck-signals?status=correct&limit=20&offset=2")

    # Then
    assert response.status_code == 200
    assert operations.list_args == (BottleneckSignalStatus.CORRECT, 20, 2)
    item = response.json()[0]
    assert item["label"] == "PRICE"
    assert "model_name" not in item
    assert "prompt_version" not in item


@pytest.mark.asyncio
async def test_detail_exposes_promotions_and_policies_without_model_metadata(app: FastAPI) -> None:
    # Given / When
    response = await _request(app, "GET", f"/agent/bottleneck-signals/{SIGNAL_ID}")

    # Then
    assert response.status_code == 200
    body = response.json()
    assert body["matched_promotions"] == [{"code": "PRICE-10"}]
    assert body["adjustment_policies"] == [{"promotion_type": "DISCOUNT"}]
    assert "model_name" not in body
    assert "prompt_version" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "status_code"),
    [("limit=0", 422), ("limit=101", 422), ("offset=-1", 422)],
)
async def test_pagination_is_bounded(app: FastAPI, query: str, status_code: int) -> None:
    response = await _request(app, "GET", f"/agent/bottleneck-signals?{query}")
    assert response.status_code == status_code


@pytest.mark.asyncio
async def test_customer_cannot_access_signal_queue(app: FastAPI) -> None:
    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="customer-1", role=Role.CUSTOMER)
    response = await _request(app, "GET", "/agent/bottleneck-signals")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_caller_cannot_access_signal_queue(app: FastAPI) -> None:
    app.dependency_overrides.pop(current_staff)
    response = await _request(app, "GET", "/agent/bottleneck-signals")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_claim_and_verdict_use_authenticated_staff_identity(app: FastAPI) -> None:
    claim = await _request(app, "POST", f"/agent/bottleneck-signals/{SIGNAL_ID}/claim")
    verdict = await _request(
        app,
        "POST",
        f"/agent/bottleneck-signals/{SIGNAL_ID}/verdict",
        json={"verdict": "CORRECT"},
    )
    assert claim.status_code == 200
    assert verdict.status_code == 200


@pytest.mark.asyncio
async def test_offer_route_submits_typed_adjustment(app: FastAPI, operations: FakeOperations) -> None:
    # Given / When
    response = await _request(
        app,
        "POST",
        f"/agent/bottleneck-signals/{SIGNAL_ID}/offer",
        json={
            "promotion_code": "PRICE-10",
            "promotion_type": "FIXED_DISCOUNT",
            "adjustment_type": "VND",
            "amount_vnd": 10_000_000,
        },
    )

    # Then
    assert response.status_code == 200
    assert operations.offer is not None
    assert operations.offer.promotion_code == "PRICE-10"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (SignalOfferConflictError(SIGNAL_ID), 409, "signal_offer_unavailable"),
        (PromotionExpiredError("expired"), 409, "promotion_expired"),
        (OfferAdjustmentOutOfBoundsError("too high"), 422, "adjustment_out_of_bounds"),
    ],
)
async def test_offer_route_maps_safe_errors(
    app: FastAPI,
    operations: FakeOperations,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    # Given
    operations.offer_error = error

    # When
    response = await _request(
        app,
        "POST",
        f"/agent/bottleneck-signals/{SIGNAL_ID}/offer",
        json={"promotion_code": "PRICE-10", "promotion_type": "FIXED_DISCOUNT"},
    )

    # Then
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
