"""Typed Auth configuration with fail-fast validation.

Auth refuses to serve traffic on a misconfigured deployment rather than falling
back to a weaker mode. Every check here runs at import/startup time so an
operator learns about a problem before the first request, not after a token has
already been issued under a weak key.

Two design rules are deliberate:

* Security contract values (token lifetimes, cookie names and paths, Argon2id
  parameters) live in `src.auth.contracts` as constants and are exposed here as
  read-only properties. They are not environment variables, so a deployment
  cannot silently shorten a cookie's protection or extend a reset token.
* Secrets are `SecretStr` and the database URL is excluded from `repr`, so a
  validation failure or log line cannot echo a credential (`AGENTS.md:43`).
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Final, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.auth import contracts

REQUIRED_DATABASE_DRIVER: Final[str] = "postgresql+asyncpg"
MIN_SECRET_LENGTH: Final[int] = 32
MIN_SECRET_DISTINCT_CHARS: Final[int] = 10
MAX_SECRET_CHAR_SHARE: Final[float] = 0.4

# Substrings that mark a value as a template placeholder rather than a real
# secret. `.env.example` ships such placeholders on purpose, so a deployment
# that forgets to replace one must fail instead of running on a known value.
PLACEHOLDER_MARKERS: Final[tuple[str, ...]] = (
    "change",
    "your",
    "placeholder",
    "example",
    "todo",
    "xxx",
    "dummy",
    "insecure",
    "generate",
)


class AuthConfigurationError(ValueError):
    """Raised when Auth configuration is unsafe or incomplete."""


def _split_origins(raw: str) -> Iterator[str]:
    for candidate in raw.split(","):
        stripped = candidate.strip()
        if stripped:
            yield stripped


def _normalize_origin(origin: str) -> str:
    """Return `scheme://host[:port]` lowercased, rejecting anything else.

    An allowed origin is an origin, not a URL: a path, query, or fragment means
    the operator misunderstood the setting, and silently truncating it would
    widen the allowlist beyond what they wrote.
    """
    trimmed = origin.strip().rstrip("/")
    parts = urlsplit(trimmed)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise AuthConfigurationError(f"cors_origins entry {parts.scheme or 'value'!r} is not a valid http(s) origin")
    if parts.path or parts.query or parts.fragment:
        raise AuthConfigurationError("cors_origins entries must not contain a path, query, or fragment")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _parse_origin_list(raw: str) -> list[str]:
    """Normalize and de-duplicate a comma-separated origin list, order preserved."""
    seen: dict[str, None] = {}
    for entry in _split_origins(raw):
        if entry == "*":
            raise AuthConfigurationError(
                "cors_origins must not use the wildcard '*' because Auth sends credentialed requests"
            )
        seen.setdefault(_normalize_origin(entry), None)
    return list(seen)


def _assert_strong_secret(field_name: str, value: str) -> None:
    """Reject short, low-entropy, and placeholder secrets.

    This is a coarse floor, not an entropy estimator. It exists to catch the
    realistic failure modes: an unset variable, a copied placeholder, and a
    padded value such as `aaaa...`.
    """
    if len(value) < MIN_SECRET_LENGTH:
        raise AuthConfigurationError(
            f"{field_name} must be at least {MIN_SECRET_LENGTH} characters when Auth is enabled"
        )
    lowered = value.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            raise AuthConfigurationError(
                f"{field_name} still contains the placeholder marker {marker!r}; generate a real secret"
            )
    distinct = set(value)
    dominant_share = max(value.count(char) for char in distinct) / len(value)
    if len(distinct) < MIN_SECRET_DISTINCT_CHARS or dominant_share > MAX_SECRET_CHAR_SHARE:
        raise AuthConfigurationError(f"{field_name} has insufficient entropy; use a random secret")


class AuthSettings(BaseSettings):
    """Auth configuration read from `AUTH_*` environment variables.

    `enabled=False` keeps legacy-only deployments working untouched: no Auth
    setting is required and no Auth resource is created.
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    enabled: bool = False

    # Shared with the legacy application settings, so this reads plain `APP_ENV`
    # rather than `AUTH_APP_ENV`. Production tightens cookie and origin rules.
    app_env: Literal["development", "production", "test"] = Field(default="development", validation_alias="APP_ENV")

    # Excluded from `repr` because a PostgreSQL URL embeds a password, and a
    # validation error renders the model.
    database_url: str = Field(default="", repr=False)

    jwt_signing_key: SecretStr = SecretStr("")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "p150-auth"
    jwt_audience: str = "p150-app"

    csrf_secret: SecretStr = SecretStr("")

    cors_origins: str = ""
    frontend_origin: str = ""

    # Overridable only outside production, where tests and local HTTP runs need it.
    cookie_secure: bool = True

    sendgrid_api_key: SecretStr = SecretStr("")
    sendgrid_from_email: str = ""

    #: `False` -> khach dang ky xong dung duoc ngay, khong can bam link trong thu.
    #:
    #: Mac dinh BAT. Tat la mot quyet dinh van hanh tuong minh cho giai doan nha
    #: cung cap thu chua chay duoc: bat xac minh qua thu khi thu khong gui noi
    #: nghia la KHONG AI dang ky duoc, va mot lop chong lam dung khong bao ve
    #: duoc gi tren mot san pham khong ai dung duoc.
    #:
    #: Danh doi khi tat: nguoi ta dang ky duoc bang dia chi thu cua nguoi khac.
    #: Bat lai ngay khi duong gui thu thong.
    require_email_verification: bool = True

    #: Danh sách domain khách được đăng ký, ngăn cách bằng dấu phẩy. Bỏ trống thì
    #: dùng `CUSTOMER_EMAIL_DOMAINS` trong domain layer. Chỉ nhận Gmail như trước
    #: thì đặt `AUTH_CUSTOMER_EMAIL_DOMAINS=gmail.com`.
    customer_email_domains: str = ""

    #: Đăng nhập Google (OAuth 2.0). Ba biến này KHÔNG mang tiền tố `AUTH_`:
    #: tên do Google Cloud Console cấp và đã nằm sẵn trong `.env` triển khai.
    #: Bỏ trống bất kỳ biến nào → tính năng tắt, endpoint Google trả 404.
    google_oauth_client_id: str = Field(default="", validation_alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: SecretStr = Field(default=SecretStr(""), validation_alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_url: str = Field(default="", validation_alias="GOOGLE_OAUTH_REDIRECT_URL")

    login_rate_limit_attempts: int = Field(default=5, ge=1)
    login_rate_limit_window_seconds: int = Field(default=900, ge=1)
    recovery_rate_limit_attempts: int = Field(default=3, ge=1)
    recovery_rate_limit_window_seconds: int = Field(default=3600, ge=1)

    @classmethod
    def env_configurable_fields(cls) -> tuple[str, ...]:
        """Field names configurable through `AUTH_*` variables.

        `app_env` is excluded: it is the shared `APP_ENV` variable and is already
        documented as such. The `google_oauth_*` fields are excluded for the same
        reason: they read their own `GOOGLE_OAUTH_*` names, documented separately
        in `.env.example`. Parity for `AUTH_*` is asserted against this list.
        """
        return tuple(name for name in cls.model_fields if name != "app_env" and not name.startswith("google_oauth"))

    @field_validator("frontend_origin", "cors_origins", "sendgrid_from_email", "jwt_issuer", "jwt_audience")
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @field_validator("frontend_origin")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def _validate_enabled_configuration(self) -> "AuthSettings":
        if not self.enabled:
            return self

        self._validate_database_url()
        self._validate_secrets()
        self._validate_identifiers()
        self._validate_origins()
        self._validate_cookie_policy()
        return self

    def _validate_database_url(self) -> None:
        if not self.database_url:
            raise AuthConfigurationError("database_url is required when Auth is enabled")
        # Compare only the driver prefix; the rest of the URL holds the password
        # and must never reach an error message.
        driver = self.database_url.split("://", 1)[0]
        if driver != REQUIRED_DATABASE_DRIVER:
            raise AuthConfigurationError(
                f"database_url must use the {REQUIRED_DATABASE_DRIVER} driver; "
                f"Auth never falls back to SQLite or a synchronous driver"
            )
        if "://" not in self.database_url or not urlsplit(self.database_url).hostname:
            raise AuthConfigurationError("database_url is not a valid connection URL")

    def _validate_secrets(self) -> None:
        signing_key = self.jwt_signing_key.get_secret_value()
        csrf_secret = self.csrf_secret.get_secret_value()

        if not signing_key:
            raise AuthConfigurationError("jwt_signing_key is required when Auth is enabled")
        _assert_strong_secret("jwt_signing_key", signing_key)

        if not csrf_secret:
            raise AuthConfigurationError("csrf_secret is required when Auth is enabled")
        _assert_strong_secret("csrf_secret", csrf_secret)

        if signing_key == csrf_secret:
            raise AuthConfigurationError("jwt_signing_key and csrf_secret must be distinct secrets")

    def _validate_identifiers(self) -> None:
        for name in ("jwt_issuer", "jwt_audience"):
            if not getattr(self, name):
                raise AuthConfigurationError(f"{name} is required when Auth is enabled")

    def _validate_origins(self) -> None:
        if not self.frontend_origin:
            raise AuthConfigurationError("frontend_origin is required when Auth is enabled")
        if not self.cors_origins:
            raise AuthConfigurationError("cors_origins is required when Auth is enabled")

        origins = _parse_origin_list(self.cors_origins)
        if not origins:
            raise AuthConfigurationError("cors_origins must list at least one origin when Auth is enabled")

        if self.is_production:
            insecure = [origin for origin in origins if not origin.startswith("https://")]
            if insecure:
                raise AuthConfigurationError("cors_origins must use https in production")
            if not self.frontend_origin.startswith("https://"):
                raise AuthConfigurationError("frontend_origin must use https in production")

    def _validate_cookie_policy(self) -> None:
        if self.is_production and not self.cookie_secure:
            raise AuthConfigurationError(
                "cookie_secure cannot be disabled in production; "
                "the __Host-/__Secure- cookie prefixes require the Secure attribute"
            )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def google_oauth_enabled(self) -> bool:
        """Đủ bộ ba `GOOGLE_OAUTH_*` thì bật; thiếu bất kỳ biến nào thì tắt."""
        return bool(
            self.google_oauth_client_id
            and self.google_oauth_client_secret.get_secret_value()
            and self.google_oauth_redirect_url
        )

    @property
    def customer_email_domain_set(self) -> frozenset[str]:
        """Domain khách được phép, đã chuẩn hóa. Rỗng → domain layer dùng mặc định."""
        entries = {part.strip().lower().lstrip("@") for part in self.customer_email_domains.split(",")}
        return frozenset(entry for entry in entries if entry)

    @property
    def cors_origin_list(self) -> list[str]:
        """Exact allowed origins, normalized and de-duplicated."""
        if not self.cors_origins:
            return []
        return _parse_origin_list(self.cors_origins)

    # ---- Frozen contract values (not environment-tunable) ----

    @property
    def access_ttl_seconds(self) -> int:
        return contracts.ACCESS_TOKEN_TTL_SECONDS

    @property
    def refresh_ttl_seconds(self) -> int:
        return contracts.REFRESH_TOKEN_TTL_SECONDS

    @property
    def email_verification_ttl_seconds(self) -> int:
        return contracts.EMAIL_VERIFICATION_TTL_SECONDS

    @property
    def password_reset_ttl_seconds(self) -> int:
        return contracts.PASSWORD_RESET_TTL_SECONDS

    @property
    def access_cookie_name(self) -> str:
        return contracts.ACCESS_COOKIE_NAME

    @property
    def refresh_cookie_name(self) -> str:
        return contracts.REFRESH_COOKIE_NAME

    @property
    def csrf_cookie_name(self) -> str:
        return contracts.CSRF_COOKIE_NAME

    @property
    def access_cookie_path(self) -> str:
        return contracts.ACCESS_COOKIE_PATH

    @property
    def refresh_cookie_path(self) -> str:
        return contracts.REFRESH_COOKIE_PATH

    @property
    def csrf_cookie_path(self) -> str:
        return contracts.CSRF_COOKIE_PATH

    @property
    def cookie_samesite(self) -> str:
        return contracts.COOKIE_SAMESITE

    @property
    def cookie_domain(self) -> None:
        """Always host-only. `__Host-` forbids a Domain attribute outright."""
        return None


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
