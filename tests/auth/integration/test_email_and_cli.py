"""Task 5 command and email adapter acceptance tests."""

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess, run
from types import SimpleNamespace

import anyio
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from src.auth.composition import AuthComposition, AuthStartupError
from src.auth.domain.authorization import Role
from src.auth.domain.values import NormalizedEmail, PlaintextPassword, PlaintextToken
from src.auth.infrastructure.email import (
    DeterministicEmailSender,
    EmailDeliveryError,
    LoggingEmailSender,
)
from src.auth.settings import AuthSettings

DB_URL = "postgresql+asyncpg://user:password@127.0.0.1:1/auth"
STRONG_SECRET = "u7Qx2Lm9Vt4Zb8Nr6Kc3Ye5Ws1Ad0Fg7Hj2Pl9Sn4Bv6Mz8Xq"
ANOTHER_STRONG_SECRET = "Rk3Wp8Ty1Uo6Ia4Ed9Qz2Cx7Vb5Nm0Lj3Hg8Fd6Sa1Pw4Ry7Tn"


def production_settings(*, sendgrid_api_key: str, sendgrid_from_email: str) -> AuthSettings:
    return AuthSettings(
        _env_file=None,
        enabled=True,
        app_env="production",
        database_url=DB_URL,
        jwt_signing_key=STRONG_SECRET,
        csrf_secret=ANOTHER_STRONG_SECRET,
        cors_origins="https://app.example.com",
        frontend_origin="https://app.example.com",
        sendgrid_api_key=sendgrid_api_key,
        sendgrid_from_email=sendgrid_from_email,
    )


async def skip_connectivity_check(engine: AsyncEngine, target: str) -> None:
    return None


async def skip_schema_check(engine: AsyncEngine, target: str) -> None:
    return None


@pytest.mark.asyncio
async def test_start_rejects_production_without_sendgrid_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: production Auth has sender address but no SendGrid API key.
    composition = AuthComposition(
        production_settings(sendgrid_api_key="", sendgrid_from_email="verified@example.com"),
        verify_schema=skip_schema_check,
    )
    monkeypatch.setattr(composition, "_verify_connectivity", skip_connectivity_check)

    # When: Auth composition starts.
    with pytest.raises(AuthStartupError, match="SendGrid"):
        await composition.start()


@pytest.mark.asyncio
async def test_start_rejects_production_without_sendgrid_sender_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: production Auth has API key but no verified sender address.
    composition = AuthComposition(
        production_settings(sendgrid_api_key="SG.valid-key", sendgrid_from_email=""),
        verify_schema=skip_schema_check,
    )
    monkeypatch.setattr(composition, "_verify_connectivity", skip_connectivity_check)

    # When: Auth composition starts.
    with pytest.raises(AuthStartupError, match="SendGrid"):
        await composition.start()


@pytest.mark.asyncio
async def test_start_prefers_email_sender_override_without_production_sendgrid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: production Auth has no SendGrid configuration but has an override.
    override = DeterministicEmailSender()
    composition = AuthComposition(
        production_settings(sendgrid_api_key="", sendgrid_from_email=""),
        verify_schema=skip_schema_check,
        email_sender=override,
    )
    monkeypatch.setattr(composition, "_verify_connectivity", skip_connectivity_check)

    # When: Auth composition starts.
    await composition.start()
    try:
        # Then: the explicit sender remains the configured resource.
        assert composition.resources.email_sender is override
    finally:
        await composition.shutdown()


@pytest.mark.asyncio
async def test_logging_email_sender_writes_the_temporary_password_to_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sender = LoggingEmailSender()

    with caplog.at_level(logging.WARNING):
        await sender.send_temporary_password(
            recipient=NormalizedEmail.parse("advisor@example.com"),
            password=PlaintextPassword("Temp!Pass1word"),
        )

    assert "advisor@example.com" in caplog.text
    assert "Temp!Pass1word" in caplog.text
    assert "development" in caplog.text.lower()


class TestDeterministicEmailSender:
    @pytest.mark.asyncio
    async def test_5_13_records_temporary_password_only_in_memory(self) -> None:
        sender = DeterministicEmailSender()
        password = PlaintextPassword("Temp!Password1")

        await sender.send_temporary_password(recipient=NormalizedEmail.parse("advisor@example.com"), password=password)

        assert sender.deliveries == [(NormalizedEmail.parse("advisor@example.com"), password)]

    @pytest.mark.asyncio
    async def test_6_reset_delivery_records_a_typed_token_only_in_memory(self) -> None:
        sender = DeterministicEmailSender()
        token = PlaintextToken("reset-token")

        await sender.send_password_reset(recipient=NormalizedEmail.parse("customer@gmail.com"), token=token)

        assert sender.reset_deliveries == [(NormalizedEmail.parse("customer@gmail.com"), token)]

    @pytest.mark.asyncio
    async def test_6_reset_delivery_failure_is_an_explicit_typed_error(self) -> None:
        sender = DeterministicEmailSender(fail_delivery=True)

        with pytest.raises(EmailDeliveryError):
            await sender.send_password_reset(
                recipient=NormalizedEmail.parse("customer@gmail.com"),
                token=PlaintextToken("reset-token"),
            )

    @pytest.mark.asyncio
    async def test_5_13_provider_failure_is_an_explicit_typed_error(self) -> None:
        sender = DeterministicEmailSender(fail_delivery=True)

        with pytest.raises(EmailDeliveryError):
            await sender.send_temporary_password(
                recipient=NormalizedEmail.parse("advisor@example.com"),
                password=PlaintextPassword("Temp!Password1"),
            )


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


def run_cli(*arguments: str) -> CommandResult:
    completed: CompletedProcess[str] = run(
        [sys.executable, "-m", "src.cli", *arguments],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(completed.stdout, completed.stderr, completed.returncode)


def test_5_1_cli_rejects_bootstrap_password_in_argv_and_never_echoes_it() -> None:
    secret = "NeverPrint!123"

    result = run_cli("create-admin", "--email", "admin@example.com", "--password", secret)

    assert result.returncode != 0
    assert "unrecognized arguments: --password" in result.stderr
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_5_1_cli_parser_has_no_password_destination() -> None:
    from src.cli import _parser

    parser = _parser()
    create_admin = next(
        action.choices["create-admin"]
        for action in parser._actions
        if getattr(action, "choices", None) is not None and "create-admin" in action.choices
    )
    destinations = {action.dest for action in create_admin._actions}

    assert "password" not in destinations


def test_create_staff_requires_an_actor_and_permits_only_staff_roles() -> None:
    from src.cli import _parser

    parser = _parser()
    create_staff = next(
        action.choices["create-staff"]
        for action in parser._actions
        if getattr(action, "choices", None) is not None and "create-staff" in action.choices
    )
    destinations = {action.dest for action in create_staff._actions}

    assert {"email", "actor_id", "role"}.issubset(destinations)
    assert "password" not in destinations
    assert (
        parser.parse_args(
            ["create-staff", "--email", "advisor@example.com", "--actor-id", "admin-id", "--role", "advisor"]
        ).role
        == "advisor"
    )
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["create-staff", "--email", "advisor@example.com", "--actor-id", "admin-id", "--role", "customer"]
        )


def test_create_staff_runtime_uses_sender_without_printing_temporary_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import src.cli as cli
    from tests.auth.unit.application.test_staff_auth import NOW, build_service, make_user

    service, stores, email_sender = build_service()

    async def seed_admin() -> None:
        await stores.add(make_user(identifier="admin", role=Role.ADMIN), now=NOW)

    anyio.run(seed_admin)

    class FakeComposition:
        def __init__(self, _settings: object) -> None:
            self.resources = SimpleNamespace(services=SimpleNamespace(staff=service))

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

    monkeypatch.setattr(cli, "AuthComposition", FakeComposition)
    monkeypatch.setattr(cli, "get_auth_settings", lambda: object())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "src.cli",
            "create-staff",
            "--email",
            "advisor@example.com",
            "--actor-id",
            "admin",
            "--role",
            "advisor",
        ],
    )

    assert cli._main() == 0
    captured = capsys.readouterr()
    assert email_sender.deliveries[0][0] == NormalizedEmail.parse("advisor@example.com")
    temporary_password = email_sender.deliveries[0][1].reveal()
    assert temporary_password not in captured.out
    assert temporary_password not in captured.err


def test_5_1_cli_requires_the_create_admin_command() -> None:
    result = run_cli()

    assert result.returncode != 0
    assert "create-admin" in result.stderr
