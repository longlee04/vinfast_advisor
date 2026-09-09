"""Auth settings validation tests.

These cover the Todo 1 acceptance criteria: fail-fast configuration, the frozen
TTL/cookie contract, and `.env.example` parity. Settings are always built with
`_env_file=None` so a developer's real `.env` cannot change an assertion.
"""

import re
from pathlib import Path
from typing import NotRequired, TypedDict, Unpack

import pytest
from pydantic import ValidationError

from src.auth import contracts
from src.auth.settings import AuthSettings

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

VALID_POSTGRES_URL = "postgresql+asyncpg://auth:devpassword@localhost:5432/p150_auth"
STRONG_SECRET = "u7Qx2Lm9Vt4Zb8Nr6Kc3Ye5Ws1Ad0Fg7Hj2Pl9Sn4Bv6Mz8Xq"
ANOTHER_STRONG_SECRET = "Rk3Wp8Ty1Uo6Ia4Ed9Qz2Cx7Vb5Nm0Lj3Hg8Fd6Sa1Pw4Ry7Tn"


class AuthSettingsOverrides(TypedDict):
    """Typed values permitted by the Auth settings test builder."""

    enabled: NotRequired[bool]
    app_env: NotRequired[str]
    database_url: NotRequired[str]
    jwt_signing_key: NotRequired[str]
    jwt_algorithm: NotRequired[str]
    csrf_secret: NotRequired[str]
    jwt_issuer: NotRequired[str]
    jwt_audience: NotRequired[str]
    cors_origins: NotRequired[str]
    frontend_origin: NotRequired[str]
    cookie_secure: NotRequired[bool]
    sendgrid_api_key: NotRequired[str]
    sendgrid_from_email: NotRequired[str]
    login_rate_limit_attempts: NotRequired[int]
    login_rate_limit_window_seconds: NotRequired[int]
    recovery_rate_limit_attempts: NotRequired[int]
    recovery_rate_limit_window_seconds: NotRequired[int]


def build(**overrides: Unpack[AuthSettingsOverrides]) -> AuthSettings:
    """Construct enabled Auth settings with valid defaults plus overrides."""
    values: AuthSettingsOverrides = {
        "enabled": True,
        "app_env": "production",
        "database_url": VALID_POSTGRES_URL,
        "jwt_signing_key": STRONG_SECRET,
        "csrf_secret": ANOTHER_STRONG_SECRET,
        "jwt_issuer": "p150-auth",
        "jwt_audience": "p150-app",
        "cors_origins": "https://app.p150.test",
        "frontend_origin": "https://app.p150.test",
        "sendgrid_api_key": "SG.test-key",
        "sendgrid_from_email": "noreply@p150.test",
    }
    return AuthSettings(_env_file=None, **(values | overrides))


class TestTodoOneTypeSafety:
    def test_todo_one_python_has_no_type_ignore_suppressions(self) -> None:
        todo_one_paths = (
            REPO_ROOT / "src" / "auth" / "composition.py",
            REPO_ROOT / "src" / "auth" / "settings.py",
            REPO_ROOT / "tests" / "auth" / "unit" / "test_settings.py",
            REPO_ROOT / "tests" / "auth" / "integration" / "test_lifespan.py",
        )
        suppression_marker = "# type:" + " ignore"
        assert all(suppression_marker not in path.read_text(encoding="utf-8") for path in todo_one_paths)


class TestDisabledAuthPreservesLegacy:
    def test_disabled_auth_needs_no_configuration(self) -> None:
        settings = build(enabled=False)
        assert settings.enabled is False

    def test_disabled_auth_ignores_missing_database_url(self) -> None:
        settings = build(enabled=False, database_url="")
        assert settings.enabled is False
        assert settings.database_url == ""


class TestMissingConfigurationFailsFast:
    @pytest.mark.parametrize(
        "field",
        ["database_url", "jwt_signing_key", "csrf_secret", "frontend_origin", "cors_origins"],
    )
    def test_enabled_auth_rejects_missing_required_field(self, field: str) -> None:
        with pytest.raises(ValidationError) as exc:
            build(**{field: ""})
        assert field in str(exc.value)


class TestDatabaseUrlIsPostgresOnly:
    def test_accepts_asyncpg_url(self) -> None:
        assert build().database_url == VALID_POSTGRES_URL

    @pytest.mark.parametrize(
        "url",
        [
            "sqlite:///./data/app.db",
            "sqlite+aiosqlite:///./data/auth.db",
        ],
    )
    def test_rejects_sqlite_url(self, url: str) -> None:
        with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
            build(database_url=url)

    def test_rejects_sync_postgres_driver(self) -> None:
        with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
            build(database_url="postgresql://auth:pw@localhost:5432/p150_auth")

    def test_rejects_malformed_url(self) -> None:
        with pytest.raises(ValidationError):
            build(database_url="not-a-url")

    def test_error_message_never_echoes_database_password(self) -> None:
        with pytest.raises(ValidationError) as exc:
            build(database_url="mysql://auth:supersecretpw@localhost:3306/db")
        assert "supersecretpw" not in str(exc.value)


class TestWeakSecretsFailFast:
    @pytest.mark.parametrize("secret", ["short", "changeme", "a" * 31])
    def test_rejects_weak_jwt_signing_key(self, secret: str) -> None:
        with pytest.raises(ValidationError):
            build(jwt_signing_key=secret)

    def test_rejects_low_entropy_key_of_sufficient_length(self) -> None:
        with pytest.raises(ValidationError, match="entropy"):
            build(jwt_signing_key="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    def test_rejects_placeholder_secret(self) -> None:
        with pytest.raises(ValidationError):
            build(csrf_secret="your-secret-key-change-in-production")

    def test_rejects_jwt_key_reused_as_csrf_secret(self) -> None:
        with pytest.raises(ValidationError, match="distinct"):
            build(csrf_secret=STRONG_SECRET)

    def test_secrets_are_redacted_in_repr(self) -> None:
        rendered = repr(build())
        assert STRONG_SECRET not in rendered
        assert ANOTHER_STRONG_SECRET not in rendered

    def test_secrets_are_redacted_in_model_dump(self) -> None:
        rendered = str(build().model_dump())
        assert STRONG_SECRET not in rendered
        assert ANOTHER_STRONG_SECRET not in rendered

    def test_secret_value_remains_retrievable(self) -> None:
        assert build().jwt_signing_key.get_secret_value() == STRONG_SECRET


class TestCorsPolicy:
    def test_parses_and_normalizes_exact_origins(self) -> None:
        settings = build(cors_origins=" https://App.P150.test/ , https://admin.p150.test ")
        assert settings.cors_origin_list == ["https://app.p150.test", "https://admin.p150.test"]

    def test_rejects_wildcard_with_credentials(self) -> None:
        with pytest.raises(ValidationError, match="wildcard"):
            build(cors_origins="*")

    def test_rejects_insecure_origin_in_production(self) -> None:
        with pytest.raises(ValidationError, match="https"):
            build(cors_origins="http://app.p150.test")

    def test_allows_localhost_http_in_development(self) -> None:
        settings = build(app_env="development", cors_origins="http://localhost:3000")
        assert settings.cors_origin_list == ["http://localhost:3000"]

    def test_rejects_origin_with_path(self) -> None:
        with pytest.raises(ValidationError, match="path"):
            build(cors_origins="https://app.p150.test/login")

    def test_deduplicates_repeated_origins(self) -> None:
        settings = build(cors_origins="https://app.p150.test,https://app.p150.test")
        assert settings.cors_origin_list == ["https://app.p150.test"]

    def test_rejects_empty_entries_only(self) -> None:
        with pytest.raises(ValidationError):
            build(cors_origins=" , ")


class TestFrontendOrigin:
    def test_rejects_insecure_frontend_origin_in_production(self) -> None:
        with pytest.raises(ValidationError, match="https"):
            build(frontend_origin="http://app.p150.test")

    def test_strips_trailing_slash(self) -> None:
        assert build(frontend_origin="https://app.p150.test/").frontend_origin == "https://app.p150.test"


class TestCookieContract:
    def test_cookie_names_match_frozen_contract(self) -> None:
        settings = build()
        assert settings.access_cookie_name == "__Host-p150_access"
        assert settings.refresh_cookie_name == "__Secure-p150_refresh"
        assert settings.csrf_cookie_name == "__Host-p150_csrf"

    def test_cookie_paths_match_frozen_contract(self) -> None:
        settings = build()
        assert settings.access_cookie_path == "/"
        assert settings.refresh_cookie_path == "/api/v1/auth"
        assert settings.csrf_cookie_path == "/"

    def test_cookies_are_always_secure_and_host_only(self) -> None:
        settings = build()
        assert settings.cookie_secure is True
        assert settings.cookie_samesite == "lax"
        assert settings.cookie_domain is None

    def test_host_prefixed_cookies_must_use_root_path(self) -> None:
        """`__Host-` requires Path=/; the refresh cookie therefore uses `__Secure-`."""
        for name, path in (
            (contracts.ACCESS_COOKIE_NAME, contracts.ACCESS_COOKIE_PATH),
            (contracts.CSRF_COOKIE_NAME, contracts.CSRF_COOKIE_PATH),
        ):
            assert name.startswith(contracts.HOST_PREFIX)
            assert path == "/"
        assert contracts.REFRESH_COOKIE_NAME.startswith(contracts.SECURE_PREFIX)
        assert not contracts.REFRESH_COOKIE_NAME.startswith(contracts.HOST_PREFIX)
        assert contracts.REFRESH_COOKIE_PATH == "/api/v1/auth"

    def test_insecure_cookie_override_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError, match="Secure"):
            build(cookie_secure=False)

    def test_insecure_cookie_allowed_only_outside_production(self) -> None:
        settings = build(app_env="development", cors_origins="http://localhost:3000", cookie_secure=False)
        assert settings.cookie_secure is False


class TestTokenTtlContract:
    def test_ttls_match_frozen_contract(self) -> None:
        settings = build()
        assert settings.access_ttl_seconds == 15 * 60
        assert settings.refresh_ttl_seconds == 30 * 24 * 60 * 60
        assert settings.email_verification_ttl_seconds == 24 * 60 * 60
        assert settings.password_reset_ttl_seconds == 60 * 60

    def test_ttls_are_not_environment_tunable(self) -> None:
        """TTLs are security contract, so unknown env overrides must not apply."""
        settings = build(enabled=False)
        assert settings.access_ttl_seconds == contracts.ACCESS_TOKEN_TTL_SECONDS


class TestJwtContract:
    def test_algorithm_defaults_to_hs256(self) -> None:
        assert build().jwt_algorithm == "HS256"

    def test_rejects_none_algorithm(self) -> None:
        with pytest.raises(ValidationError):
            build(jwt_algorithm="none")

    def test_rejects_unsupported_algorithm(self) -> None:
        with pytest.raises(ValidationError):
            build(jwt_algorithm="HS1")

    def test_issuer_and_audience_are_required_when_enabled(self) -> None:
        with pytest.raises(ValidationError):
            build(jwt_issuer="")

    def test_no_previous_key_grace_field_exists(self) -> None:
        """MVP explicitly defers previous-key grace (plan Must NOT)."""
        assert "previous" not in " ".join(AuthSettings.model_fields).lower()


class TestRateLimitPolicy:
    def test_defaults_are_bounded_and_positive(self) -> None:
        settings = build()
        assert settings.login_rate_limit_attempts > 0
        assert settings.login_rate_limit_window_seconds > 0
        assert settings.recovery_rate_limit_attempts > 0
        assert settings.recovery_rate_limit_window_seconds > 0

    @pytest.mark.parametrize("value", [0, -1])
    def test_rejects_non_positive_attempts(self, value: int) -> None:
        with pytest.raises(ValidationError):
            build(login_rate_limit_attempts=value)


class TestEnvExampleParity:
    """Every Auth setting must be documented in `.env.example` (Todo 1 criterion)."""

    @staticmethod
    def documented_names() -> set[str]:
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        return set(re.findall(r"^#?\s*(AUTH_[A-Z0-9_]+)=", text, flags=re.MULTILINE))

    def test_every_auth_field_is_documented(self) -> None:
        expected = {f"AUTH_{name.upper()}" for name in AuthSettings.env_configurable_fields()}
        assert expected <= self.documented_names()

    def test_no_undocumented_auth_variable_is_advertised(self) -> None:
        known = {f"AUTH_{name.upper()}" for name in AuthSettings.env_configurable_fields()}
        assert self.documented_names() <= known

    def test_env_example_holds_no_real_credential(self) -> None:
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "SG." not in text.split("AUTH_SENDGRID_API_KEY=")[-1].splitlines()[0]
        for line in text.splitlines():
            if line.startswith("AUTH_JWT_SIGNING_KEY=") or line.startswith("AUTH_CSRF_SECRET="):
                value = line.split("=", 1)[1]
                assert value == "" or "change" in value.lower() or "generate" in value.lower()
