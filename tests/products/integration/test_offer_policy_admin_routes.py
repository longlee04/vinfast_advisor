"""Integration tests for the ADMIN offer-policy CRUD routes."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.domain.authorization import Role
from src.products.application.offer_policy_service import OfferPolicyService
from src.products.infrastructure.repositories import SqlAlchemyOfferPolicyRepository
from src.products.presentation.routes import router as products_router

PRODUCT_API_PREFIX = "/api/v1"


class _CustomerStub:
    """Fake customer.me() — return the configured user for any access token."""

    def __init__(self, user: SimpleNamespace) -> None:
        self._user = user

    async def me(self, access_token: str) -> SimpleNamespace:
        return self._user


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), role=Role.ADMIN)


def _advisor_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), role=Role.ADVISOR)


async def _make_app(session_factory, user: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(products_router, prefix=PRODUCT_API_PREFIX)
    repo = SqlAlchemyOfferPolicyRepository(session_factory)
    app.state.product = SimpleNamespace(
        offer_policy_service=OfferPolicyService(repo),
        vehicle_service=None,
        feature_flag_service=None,
        tco_service=None,
    )
    app.state.auth = SimpleNamespace(
        resources=SimpleNamespace(services=SimpleNamespace(customer=_CustomerStub(user))),
    )
    return app


async def _request(app: FastAPI, method: str, path: str, json=None) -> tuple[int, dict]:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"__Host-p150_access": "token"},
    ) as client:
        response = await client.request(method, f"{PRODUCT_API_PREFIX}{path}", json=json)
        try:
            body = response.json()
        except Exception:
            body = {}
        return response.status_code, body


@pytest.mark.asyncio
async def test_admin_creates_policy_201(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _admin_user())

    # When
    status_code, body = await _request(
        app,
        "POST",
        "/admin/offer-policies",
        json={"promotion_type": "FIXED_DISCOUNT", "adjust_min_vnd": 0, "adjust_max_vnd": 5_000_000},
    )

    # Then
    assert status_code == 201
    assert body["data"]["promotion_type"] == "FIXED_DISCOUNT"
    assert body["data"]["adjust_max_vnd"] == 5_000_000


@pytest.mark.asyncio
async def test_admin_patch_policy_200(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _admin_user())
    await _request(
        app,
        "POST",
        "/admin/offer-policies",
        json={"promotion_type": "FINANCING", "financing_months_min": 6, "financing_months_max": 36},
    )

    # When
    status_code, body = await _request(
        app,
        "PATCH",
        "/admin/offer-policies/FINANCING",
        json={"financing_support_max_vnd": 25_000_000},
    )

    # Then
    assert status_code == 200
    assert body["data"]["financing_support_max_vnd"] == 25_000_000
    assert body["data"]["financing_months_max"] == 36


@pytest.mark.asyncio
async def test_admin_list_policies_200(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _admin_user())
    await _request(
        app,
        "POST",
        "/admin/offer-policies",
        json={"promotion_type": "GIFT", "gift_value_max_vnd": 3_000_000},
    )

    # When
    status_code, body = await _request(app, "GET", "/admin/offer-policies")

    # Then
    assert status_code == 200
    assert any(item["promotion_type"] == "GIFT" for item in body["data"])


@pytest.mark.asyncio
async def test_admin_delete_policy_204(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _admin_user())
    await _request(
        app,
        "POST",
        "/admin/offer-policies",
        json={"promotion_type": "OTHER", "other_max_vnd": 5_000_000},
    )

    # When
    status_code, _ = await _request(app, "DELETE", "/admin/offer-policies/OTHER")

    # Then
    assert status_code == 204


@pytest.mark.asyncio
async def test_advisor_post_policy_403(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _advisor_user())

    # When
    status_code, _ = await _request(
        app,
        "POST",
        "/admin/offer-policies",
        json={"promotion_type": "FIXED_DISCOUNT", "adjust_max_vnd": 5_000_000},
    )

    # Then
    assert status_code == 403


@pytest.mark.asyncio
async def test_admin_post_invalid_bounds_422(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _admin_user())

    # When: min > max
    status_code, body = await _request(
        app,
        "POST",
        "/admin/offer-policies",
        json={"promotion_type": "FIXED_DISCOUNT", "adjust_min_vnd": 10_000_000, "adjust_max_vnd": 0},
    )

    # Then
    assert status_code == 422
    assert "min" in body["detail"] or "exceed" in body["detail"]


@pytest.mark.asyncio
async def test_admin_post_negative_bound_422(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _admin_user())

    # When
    status_code, _ = await _request(
        app,
        "POST",
        "/admin/offer-policies",
        json={"promotion_type": "FIXED_DISCOUNT", "adjust_min_vnd": -1, "adjust_max_vnd": 0},
    )

    # Then
    assert status_code == 422


@pytest.mark.asyncio
async def test_admin_patch_missing_policy_404(product_session_factory) -> None:
    # Given
    app = await _make_app(product_session_factory, _admin_user())

    # When
    status_code, _ = await _request(app, "PATCH", "/admin/offer-policies/NOPE", json={"other_max_vnd": 1})

    # Then
    assert status_code == 404
