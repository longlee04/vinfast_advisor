"""Integration coverage for the Auth HTTP boundary."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import src.main as main_module
from src.auth.infrastructure.email import DeterministicEmailSender
from src.auth.settings import get_auth_settings


def _set_auth_env(monkeypatch: pytest.MonkeyPatch, auth_database_url: str, **overrides: str) -> None:
    """Biến môi trường Auth cho một vòng đời ứng dụng thật.

    Tách khỏi fixture vì có test cần đúng bộ này nhưng khác MỘT giá trị — chép
    lại tám dòng ở mỗi chỗ là cách chắc chắn để chúng lệch nhau về sau.
    """

    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_DATABASE_URL", auth_database_url)
    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", "jwt-signing-key-7R!v2mQ9#xK4pL8@sD6fH3nZ")
    monkeypatch.setenv("AUTH_CSRF_SECRET", "csrf-secret-3Y!q8wE2#rT7uI5@oP9aS4dF")
    monkeypatch.setenv("AUTH_CORS_ORIGINS", "https://test.example")
    monkeypatch.setenv("AUTH_FRONTEND_ORIGIN", "https://test.example")
    monkeypatch.setenv("AUTH_SENDGRID_API_KEY", "test-sendgrid-key")
    monkeypatch.setenv("AUTH_SENDGRID_FROM_EMAIL", "auth@test.example")
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)
    get_auth_settings.cache_clear()


@pytest_asyncio.fixture
async def https_client(
    auth_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """Drive the real Auth lifespan over HTTPS with deterministic adapters."""
    _set_auth_env(monkeypatch, auth_database_url)
    cors_middleware = next(
        middleware for middleware in main_module.app.user_middleware if middleware.cls is main_module.CORSMiddleware
    )
    cors_middleware.kwargs["allow_origins"] = ["https://test.example"]
    main_module.app.middleware_stack = None
    main_module.AUTH_EMAIL_SENDER_OVERRIDE = DeterministicEmailSender()
    try:
        async with main_module.app.router.lifespan_context(main_module.app):
            transport = ASGITransport(app=main_module.app)
            async with AsyncClient(
                transport=transport,
                base_url="https://test.example",
                headers={"Origin": "https://test.example"},
            ) as client:
                yield client
    finally:
        main_module.AUTH_EMAIL_SENDER_OVERRIDE = None
        get_auth_settings.cache_clear()


@pytest.mark.asyncio
async def test_staff_creation_rejects_the_customer_role(https_client: AsyncClient) -> None:
    response = await https_client.post("/api/v1/auth/staff", json={"email": "person@example.com", "role": "customer"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_staff_creation_no_longer_accepts_a_password(https_client: AsyncClient) -> None:
    response = await https_client.post(
        "/api/v1/auth/staff",
        json={"email": "person@example.com", "role": "advisor", "password": "Strong-password-123"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_staff_login_rejects_an_unknown_account(https_client: AsyncClient) -> None:
    response = await https_client.post(
        "/api/v1/auth/staff/login",
        json={"email": "nobody@example.com", "password": "Strong-password-123"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_credentials"}
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_staff_login_endpoints_are_published(https_client: AsyncClient) -> None:
    schema = (await https_client.get("/openapi.json")).json()

    assert "/api/v1/auth/staff/login" in schema["paths"]
    assert "/api/v1/auth/staff/complete-password" in schema["paths"]


@pytest.mark.asyncio
async def test_recovery_origin_is_required_without_mutating_state(https_client: AsyncClient) -> None:
    for path, payload in (
        ("/api/v1/auth/register", {"email": "origin@example.com", "password": "Strong-password-123"}),
        ("/api/v1/auth/forgot-password", {"email": "origin@example.com"}),
        ("/api/v1/auth/resend-verification", {"email": "origin@example.com"}),
    ):
        response = await https_client.post(path, headers={"Origin": "https://evil.example"}, json=payload)
        assert response.status_code == 403
        assert response.json() == {"error": "origin_forbidden"}


@pytest.mark.asyncio
async def test_reset_requires_matching_csrf_cookie_and_header(
    https_client: AsyncClient,
) -> None:
    https_client.cookies.set("__Host-p150_csrf", "csrf-cookie", domain="test.example", path="/")
    response = await https_client.post(
        "/api/v1/auth/reset-password",
        json={"token": "unknown", "password": "Strong-password-123"},
    )
    assert response.status_code == 403

    response = await https_client.post(
        "/api/v1/auth/reset-password",
        headers={"X-CSRF-Token": "wrong"},
        json={"token": "unknown", "password": "Strong-password-123"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_forgot_password_remains_generic_and_rate_limit_safe(
    https_client: AsyncClient,
) -> None:
    first = await https_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    second = await https_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json() == {"message": "password_recovery_received"}


@pytest.mark.asyncio
async def test_login_sets_exact_secure_cookie_matrix(https_client: AsyncClient) -> None:
    """Given a verified customer, login emits only the frozen cookie contract."""
    registration = await https_client.post(
        "/api/v1/auth/register",
        json={"email": "cookies@gmail.com", "password": "Strong-password-123"},
    )
    assert registration.status_code == 202
    email_sender = main_module.AUTH_EMAIL_SENDER_OVERRIDE
    assert isinstance(email_sender, DeterministicEmailSender)
    verification_token = email_sender.deliveries[0][1].reveal()
    verification = await https_client.post("/api/v1/auth/verify", json={"token": verification_token})
    assert verification.status_code == 200

    response = await https_client.post(
        "/api/v1/auth/login",
        json={"email": "cookies@gmail.com", "password": "Strong-password-123"},
    )

    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 3
    assert any(
        cookie.startswith("__Host-p150_access=")
        and "; HttpOnly;" in cookie
        and "; Path=/;" in cookie
        and "; SameSite=lax;" in cookie
        and "; Secure" in cookie
        and "Domain=" not in cookie
        for cookie in cookies
    )
    assert any(
        cookie.startswith("__Secure-p150_refresh=")
        and "; HttpOnly;" in cookie
        and "; Path=/api/v1/auth;" in cookie
        and "; SameSite=lax;" in cookie
        and "; Secure" in cookie
        and "Domain=" not in cookie
        for cookie in cookies
    )
    assert any(
        cookie.startswith("__Host-p150_csrf=")
        and "HttpOnly" not in cookie
        and "; Path=/;" in cookie
        and "; SameSite=lax;" in cookie
        and "; Secure" in cookie
        and "Domain=" not in cookie
        for cookie in cookies
    )


@pytest.mark.asyncio
async def test_refresh_requires_matching_csrf_before_cookie_authentication(https_client: AsyncClient) -> None:
    """Given a refresh cookie, a missing CSRF header is rejected before refresh mutation."""
    https_client.cookies.set("__Secure-p150_refresh", "invalid", domain="test.example", path="/api/v1/auth")

    response = await https_client.post("/api/v1/auth/refresh")

    assert response.status_code == 403
    assert response.json() == {"error": "csrf_failed"}


@pytest.mark.asyncio
async def test_cors_rejects_unknown_origin_without_wildcard_credentials(https_client: AsyncClient) -> None:
    """Given an unknown browser origin, preflight does not authorize credentialed access."""
    response = await https_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


@pytest.mark.asyncio
async def test_auth_rejects_oversized_input_without_storing_response(https_client: AsyncClient) -> None:
    """Given overlong credentials, the boundary rejects them and disables caching."""
    response = await https_client.post(
        "/api/v1/auth/login",
        json={"email": "a" * 255, "password": "Strong-password-123"},
    )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_verify_is_post_only(https_client: AsyncClient) -> None:
    """Given a verification route, GET cannot consume or validate a credential."""
    response = await https_client.get("/api/v1/auth/verify?token=unknown")

    assert response.status_code == 405


@pytest.mark.asyncio
async def test_invalid_refresh_clears_exact_cookie_paths(https_client: AsyncClient) -> None:
    """Given an invalid refresh with valid CSRF, all session cookies are cleared exactly."""
    https_client.cookies.set("__Secure-p150_refresh", "invalid", domain="test.example", path="/api/v1/auth")
    https_client.cookies.set("__Host-p150_csrf", "csrf-cookie", domain="test.example", path="/")

    response = await https_client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "csrf-cookie"})

    assert response.status_code == 401
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("__Host-p150_access=") and "; Path=/;" in cookie for cookie in cookies)
    assert any(cookie.startswith("__Secure-p150_refresh=") and "; Path=/api/v1/auth;" in cookie for cookie in cookies)
    assert any(cookie.startswith("__Host-p150_csrf=") and "; Path=/;" in cookie for cookie in cookies)
    assert all("Domain=" not in cookie for cookie in cookies)
    assert all("; HttpOnly" in cookie for cookie in cookies[:2])
    assert "; HttpOnly" not in cookies[2]
    assert all("; SameSite=lax;" in cookie for cookie in cookies)
    assert all("; Secure" in cookie for cookie in cookies)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_known_cors_origin_allows_only_credentialed_exact_origin(https_client: AsyncClient) -> None:
    """Given the configured browser origin, preflight permits credentialed POST requests."""
    response = await https_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://test.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://test.example"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.asyncio
async def test_logout_requires_csrf_before_clearing_session_cookies(https_client: AsyncClient) -> None:
    """Given cookie credentials, a missing CSRF header cannot trigger logout state mutation."""
    https_client.cookies.set("__Secure-p150_refresh", "invalid", domain="test.example", path="/api/v1/auth")
    https_client.cookies.set("__Host-p150_csrf", "csrf-cookie", domain="test.example", path="/")

    response = await https_client.post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.json() == {"error": "csrf_failed"}
    assert response.headers.get_list("set-cookie") == []


@pytest.mark.asyncio
async def test_refresh_cookie_is_not_sent_to_legacy_routes(https_client: AsyncClient) -> None:
    """Given a path-scoped refresh cookie, legacy routes receive no refresh credential."""
    https_client.cookies.set("__Secure-p150_refresh", "refresh", domain="test.example", path="/api/v1/auth")

    health = await https_client.get("/health")
    chat = await https_client.post("/api/v1/chat", json={"message": "hello"})

    assert health.status_code == 200
    assert chat.status_code != 401
    assert "__Secure-p150_refresh" not in health.request.headers.get("cookie", "")
    assert "__Secure-p150_refresh" not in chat.request.headers.get("cookie", "")


@pytest.mark.asyncio
async def test_auth_validation_error_is_never_cacheable(https_client: AsyncClient) -> None:
    """Given malformed bounded input, validation failures carry the Auth no-store contract."""
    response = await https_client.post("/api/v1/auth/login", json={"email": "a" * 255, "password": "x"})

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_a_disallowed_email_domain_says_why_instead_of_looking_successful(
    https_client: AsyncClient,
) -> None:
    """Luật allowlist miền email phải nói ra, không được đội lốt thành công.

    Cả thành công lẫn thất bại đều trả 202 nên client không phân biệt được bằng
    mã HTTP; nó đọc `message` hay `error`. Nhưng `registration_unavailable` gộp
    ba nguyên nhân khác hẳn nhau, trong đó "email ngoài allowlist" là luật công
    khai — giấu nó đi thì khách không bao giờ biết phải sửa gì.

    Ba nguyên nhân KHÔNG được gộp: miền email và mật khẩu là luật ai cũng biết
    trước khi gõ, còn "email đã đăng ký" là thông tin về tài khoản người khác.
    """

    response = await https_client.post(
        "/api/v1/auth/register",
        json={"email": "khach@10minutemail.com", "password": "Strong-password-123"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "email_domain_not_allowed"}


@pytest.mark.asyncio
async def test_a_weak_password_registration_says_which_rule_it_broke(
    https_client: AsyncClient,
) -> None:
    """Chính sách mật khẩu cũng là luật công khai — nói ra được, không lộ gì.

    Trả mã LÁ (`password_too_short`) chứ không phải mã họ: khách sửa được ngay
    thay vì đoán xem "vi phạm chính sách" là vi phạm điều nào.
    """

    response = await https_client.post(
        "/api/v1/auth/register",
        json={"email": "matkhauyeu@gmail.com", "password": "ngan"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "password_too_short"}


@pytest.mark.asyncio
async def test_a_duplicate_registration_stays_indistinguishable_from_success(
    https_client: AsyncClient,
) -> None:
    """Email đã tồn tại thì PHẢI trông y hệt lần đăng ký đầu.

    Đây là chỗ duy nhất trong ba nhánh mà sự mơ hồ là tính năng: phân biệt được
    "đã đăng ký" với "chưa" là dựng sẵn một máy dò tài khoản.
    """

    payload = {"email": "trung.lap@gmail.com", "password": "Strong-password-123"}

    first = await https_client.post("/api/v1/auth/register", json=payload)
    second = await https_client.post("/api/v1/auth/register", json=payload)

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json() == {"message": "registration_received"}


@pytest.mark.asyncio
async def test_a_dead_email_provider_does_not_destroy_the_account(
    https_client: AsyncClient,
) -> None:
    """Nhà cung cấp mail chết KHÔNG được kéo theo tài khoản vừa tạo.

    Gửi mail nằm trong transaction ghi user thì hai việc chẳng liên quan gì nhau
    bị buộc chung một số phận: SendGrid timeout → rollback cả user → khách nhận
    500 và không có tài khoản nào. Ghi bền trước, chuyển phát sau: mail hỏng thì
    tài khoản vẫn còn, khách bấm "gửi lại thư xác minh" là đi tiếp được.
    """

    sender = main_module.AUTH_EMAIL_SENDER_OVERRIDE
    assert isinstance(sender, DeterministicEmailSender)
    email = "mail.chet@gmail.com"
    password = "Strong-password-123"

    sender.fail_delivery = True
    try:
        registration = await https_client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        )
    finally:
        sender.fail_delivery = False

    # Bản ghi đã bền — nên với khách, lượt này KHÔNG phải một lỗi hệ thống.
    assert registration.status_code == 202
    assert registration.json() == {"message": "registration_received"}

    # Bằng chứng tài khoản còn sống: gửi lại thư xác minh phải ra được token, và
    # token đó kích hoạt được tài khoản. Nếu user bị rollback thì `resend` im
    # lặng không phát gì (nó cố tình không tiết lộ email có tồn tại hay không).
    sender.deliveries.clear()
    resend = await https_client.post(
        "/api/v1/auth/resend-verification",
        headers={"Origin": get_auth_settings().frontend_origin},
        json={"email": email},
    )
    assert resend.status_code == 200
    assert sender.deliveries, "tai khoan da bi rollback: khong con gi de gui lai"

    token = sender.deliveries[-1][1].reveal()
    verification = await https_client.post("/api/v1/auth/verify", json={"token": token})
    assert verification.status_code == 200

    login = await https_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_registration_works_end_to_end_without_email_when_verification_is_off(
    auth_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Công tắc tắt: đăng ký rồi đăng nhập được ngay, KHÔNG cần một lá thư nào.

    Đây là ca vận hành thật đã gặp trên prod: nhà cung cấp thư từ chối, và vì
    xác minh là bắt buộc nên không một khách nào đăng ký nổi. Test chạy trọn
    đường HTTP với `fail_delivery=True` để chứng minh đường đăng ký không còn
    phụ thuộc vào việc thư có rời được máy chủ hay không.
    """

    _set_auth_env(monkeypatch, auth_database_url, AUTH_REQUIRE_EMAIL_VERIFICATION="false")
    sender = DeterministicEmailSender(fail_delivery=True)
    main_module.AUTH_EMAIL_SENDER_OVERRIDE = sender
    credentials = {"email": "mail.chet.van.dang.ky@gmail.com", "password": "Strong-password-123"}
    try:
        async with main_module.app.router.lifespan_context(main_module.app):
            transport = ASGITransport(app=main_module.app)
            async with AsyncClient(
                transport=transport,
                base_url="https://test.example",
                headers={"Origin": get_auth_settings().frontend_origin},
            ) as client:
                registration = await client.post("/api/v1/auth/register", json=credentials)
                login = await client.post("/api/v1/auth/login", json=credentials)
    finally:
        main_module.AUTH_EMAIL_SENDER_OVERRIDE = None
        get_auth_settings.cache_clear()

    assert registration.status_code == 202
    assert registration.json() == {"message": "registration_received"}
    assert sender.deliveries == [], "tat xac minh thi khong duoc goi nha cung cap thu"
    assert login.status_code == 200, "dang ky xong phai dang nhap duoc ngay"
