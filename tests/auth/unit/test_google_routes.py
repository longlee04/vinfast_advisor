"""HTTP tests cho /auth/google/start và /auth/google/callback.

Dịch vụ Google được fake; các bài này kiểm HỢP ĐỒNG HTTP: chuyển hướng sang
Google kèm cookie state, so state cứng tay ở callback, phát đúng bộ cookie
phiên như /auth/login khi thành công, và đưa khách về /login?error=google khi
không thành — không bao giờ 500 giữa chừng luồng chuyển hướng.
"""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.domain.values import PlaintextToken
from src.auth.presentation.routes import router

CLIENT_ID = "test-client.apps.googleusercontent.com"
REDIRECT_URL = "https://example.test/api/v1/auth/google/callback"
STATE_COOKIE = "__Host-p150_oauth_state"


class FakeGoogleService:
    def __init__(self, session: object | None) -> None:
        self.session = session
        self.codes: list[str] = []

    async def login_with_google(self, code: str) -> object | None:
        self.codes.append(code)
        return self.session


def fake_session() -> SimpleNamespace:
    return SimpleNamespace(access_token="access-token-value", refresh_token=PlaintextToken("refresh-token-value"))


def build_app(*, google_enabled: bool = True, session: object | None = None) -> tuple[FastAPI, FakeGoogleService]:
    application = FastAPI()
    service = FakeGoogleService(session)
    application.state.auth = SimpleNamespace(
        enabled=True,
        google_oauth_enabled=google_enabled,
        google_oauth_client_id=CLIENT_ID,
        google_oauth_redirect_url=REDIRECT_URL,
        resources=SimpleNamespace(services=SimpleNamespace(google=service)),
    )
    application.include_router(router)
    return application, service


def client_for(app: FastAPI, cookies: dict[str, str] | None = None) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test", cookies=cookies or {})


@pytest.mark.asyncio
async def test_start_redirects_to_google_with_matching_state_cookie() -> None:
    app, _ = build_app()
    async with client_for(app) as client:
        response = await client.get("/auth/google/start")

    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.scheme == "https"
    assert location.netloc == "accounts.google.com"
    assert location.path == "/o/oauth2/v2/auth"
    params = parse_qs(location.query)
    assert params["client_id"] == [CLIENT_ID]
    assert params["redirect_uri"] == [REDIRECT_URL]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["openid email profile"]
    assert params["prompt"] == ["select_account"]

    set_cookie = "; ".join(response.headers.get_list("set-cookie"))
    assert STATE_COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "Max-Age=600" in set_cookie
    # Cookie state phải trùng đúng state gửi sang Google.
    assert response.cookies[STATE_COOKIE] == params["state"][0]


@pytest.mark.asyncio
async def test_start_is_404_when_google_oauth_is_off() -> None:
    app, _ = build_app(google_enabled=False)
    async with client_for(app) as client:
        response = await client.get("/auth/google/start")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_callback_refuses_state_mismatch() -> None:
    app, service = build_app(session=fake_session())
    async with client_for(app, cookies={STATE_COOKIE: "state-goc"}) as client:
        response = await client.get("/auth/google/callback", params={"code": "abc", "state": "state-khac"})
    assert response.status_code == 400
    assert service.codes == []


@pytest.mark.asyncio
async def test_callback_refuses_missing_state_cookie() -> None:
    app, service = build_app(session=fake_session())
    async with client_for(app) as client:
        response = await client.get("/auth/google/callback", params={"code": "abc", "state": "state-goc"})
    assert response.status_code == 400
    assert service.codes == []


@pytest.mark.asyncio
async def test_callback_success_sets_session_cookies_and_redirects_home() -> None:
    app, service = build_app(session=fake_session())
    async with client_for(app, cookies={STATE_COOKIE: "state-goc"}) as client:
        response = await client.get("/auth/google/callback", params={"code": "abc", "state": "state-goc"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert service.codes == ["abc"]
    set_cookies = response.headers.get_list("set-cookie")
    names = {cookie.split("=", 1)[0] for cookie in set_cookies}
    assert {"__Host-p150_access", "__Secure-p150_refresh", "__Host-p150_csrf"} <= names
    # Cookie state dùng một lần: phải bị xoá ngay trong callback.
    state_cookie_lines = [cookie for cookie in set_cookies if cookie.startswith(f"{STATE_COOKIE}=")]
    assert state_cookie_lines and "Max-Age=0" in state_cookie_lines[0]


@pytest.mark.asyncio
async def test_callback_failure_redirects_to_login_with_error() -> None:
    app, _ = build_app(session=None)
    async with client_for(app, cookies={STATE_COOKIE: "state-goc"}) as client:
        response = await client.get("/auth/google/callback", params={"code": "abc", "state": "state-goc"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/login?error=google"
    names = {cookie.split("=", 1)[0] for cookie in response.headers.get_list("set-cookie")}
    assert "__Host-p150_access" not in names


@pytest.mark.asyncio
async def test_callback_without_code_redirects_to_login_with_error() -> None:
    """Khách bấm Hủy ở màn Google: Google gọi về không có `code` — đó là một
    kết cục bình thường, không phải lỗi hệ thống."""
    app, service = build_app(session=fake_session())
    async with client_for(app, cookies={STATE_COOKIE: "state-goc"}) as client:
        response = await client.get("/auth/google/callback", params={"state": "state-goc"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/login?error=google"
    assert service.codes == []


@pytest.mark.asyncio
async def test_callback_is_404_when_google_oauth_is_off() -> None:
    app, _ = build_app(google_enabled=False)
    async with client_for(app, cookies={STATE_COOKIE: "s"}) as client:
        response = await client.get("/auth/google/callback", params={"code": "abc", "state": "s"})
    assert response.status_code == 404
