"""Executable contracts for the shipped Auth MVP documentation."""

from pathlib import Path

from src.auth import contracts
from src.auth.settings import AuthSettings

README = Path("README.md")
ENV_EXAMPLE = Path(".env.example")


def test_readme_documents_every_auth_environment_variable() -> None:
    # Given
    readme = README.read_text(encoding="utf-8")
    expected = {f"AUTH_{name.upper()}" for name in AuthSettings.env_configurable_fields()}

    # When
    missing = sorted(name for name in expected if name not in readme)

    # Then
    assert missing == []
    assert "APP_ENV" in readme


def test_readme_documents_shipped_commands_and_auth_endpoints() -> None:
    # Given
    readme = README.read_text(encoding="utf-8")
    endpoints = (
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/verify",
        "/api/v1/auth/resend-verification",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/staff",
        "/api/v1/auth/staff/login",
        "/api/v1/auth/staff/complete-password",
        "/api/v1/auth/admin/users",
        "/api/v1/auth/admin/users/{user_id}/role",
        "/api/v1/auth/admin/users/{user_id}/disable",
        "/api/v1/auth/admin/users/{user_id}/enable",
    )
    commands = (
        "uv sync --locked",
        "docker compose up -d postgres",
        "uv run alembic -c alembic-auth.ini upgrade head",
        "uv run python -m src.cli create-admin --email",
        "uv run python -m src.cli create-staff --email",
        "uv run uvicorn src.main:app",
    )

    # When / Then
    for value in (*endpoints, *commands):
        assert value in readme


def test_readme_documents_frozen_cookie_and_ttl_contracts() -> None:
    # Given
    readme = README.read_text(encoding="utf-8")
    frozen_values = (
        contracts.ACCESS_COOKIE_NAME,
        contracts.REFRESH_COOKIE_NAME,
        contracts.CSRF_COOKIE_NAME,
        contracts.ACCESS_COOKIE_PATH,
        contracts.REFRESH_COOKIE_PATH,
        contracts.CSRF_HEADER_NAME,
        str(contracts.ACCESS_TOKEN_TTL_SECONDS),
        str(contracts.REFRESH_TOKEN_TTL_SECONDS),
        str(contracts.EMAIL_VERIFICATION_TTL_SECONDS),
        str(contracts.PASSWORD_RESET_TTL_SECONDS),
        str(contracts.TEMPORARY_PASSWORD_TTL_SECONDS),
    )

    # When / Then
    for value in frozen_values:
        assert value in readme
    assert "HttpOnly" in readme
    assert "SameSite=Lax" in readme
    assert "Domain" in readme


def test_readme_documents_temporary_staff_recovery_contract() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "expired temporary password" in readme
    assert "forgot-password" in readme
    assert "reset-password" in readme
    assert "TEMPORARY_PASSWORD" in readme
    assert "ACTIVE" in readme


def test_readme_documents_roles_states_and_deferred_hardening_without_secrets() -> None:
    # Given
    readme = README.read_text(encoding="utf-8")
    required = (
        "CUSTOMER",
        "ADVISOR",
        "ADMIN",
        "PENDING_VERIFICATION",
        "TEMPORARY_PASSWORD",
        "ACTIVE",
        "DISABLED",
        "Deferred hardening",
        "OAuth",
        "MFA",
        "backup/restore",
        "multi-replica",
    )

    # When / Then
    for value in required:
        assert value in readme
    assert "requirements.txt" not in readme
    assert "AUTH_JWT_SIGNING_KEY=ci-" not in readme
    assert "AUTH_CSRF_SECRET=ci-" not in readme


def test_env_example_and_readme_use_the_same_auth_environment_names() -> None:
    # Given
    readme = README.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    expected = {f"AUTH_{name.upper()}" for name in AuthSettings.env_configurable_fields()}

    # When / Then
    for name in expected:
        assert name in env_example
        assert name in readme
