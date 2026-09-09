"""Seam danh tinh khach phai duoc noi vao phien dang nhap Auth trong app that."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from src.agents.api.dependencies import get_current_customer_id
from src.agents.composition import AgentComposition
from src.main import _customer_id_from_auth, _wire_agent_operations


def test_customer_identity_seam_is_overridden_even_without_agent_database() -> None:
    """Seam khach khong phu thuoc vao viec agent co database hay khong."""
    application = FastAPI()

    _wire_agent_operations(application, AgentComposition(database_url=""))

    assert application.dependency_overrides[get_current_customer_id] is _customer_id_from_auth


@pytest.mark.asyncio
async def test_customer_id_is_none_when_auth_session_is_absent(monkeypatch) -> None:
    """Chua dang nhap thi tra None, khong raise — route tu quyet dinh 401."""

    async def _no_identity(_request: object) -> None:
        return None

    monkeypatch.setattr("src.main._auth_identity", _no_identity)

    assert await _customer_id_from_auth(object()) is None


@pytest.mark.asyncio
async def test_customer_id_is_the_authenticated_user_id(monkeypatch) -> None:
    """Dinh danh khach lay tu Auth, khong lay tu body request."""

    async def _identity(_request: object) -> tuple[str, object]:
        return "user-42", object()

    monkeypatch.setattr("src.main._auth_identity", _identity)

    assert await _customer_id_from_auth(object()) == "user-42"
