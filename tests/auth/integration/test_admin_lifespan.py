"""Lifespan coverage for disabled administrative Auth routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.composition import AuthStartupError
from src.auth.settings import get_auth_settings
from src.main import app


@pytest.mark.asyncio
async def test_admin_routes_stay_closed_when_auth_is_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given AUTH_ENABLED=false, when lifespan runs, then Auth resources remain unavailable."""
    monkeypatch.setenv("AUTH_ENABLED", "false")
    get_auth_settings.cache_clear()
    transport = ASGITransport(app=app)
    try:
        async with app.router.lifespan_context(app):
            assert app.state.auth.enabled is False
            with pytest.raises(AuthStartupError):
                _ = app.state.auth.resources
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                listing = await client.get("/api/v1/auth/admin/users")
                enable = await client.post("/api/v1/auth/admin/users/target/enable")
                disable = await client.post("/api/v1/auth/admin/users/target/disable")
    finally:
        get_auth_settings.cache_clear()

    assert listing.status_code == 401
    assert listing.json() == {"error": "invalid_session"}
    assert listing.headers["cache-control"] == "no-store"
    assert enable.status_code == 403
    assert enable.json() == {"error": "csrf_failed"}
    assert disable.status_code == 403
    assert disable.json() == {"error": "csrf_failed"}
