"""Auth lifespan and composition integration tests.

These cover the Todo 1 startup contract: Auth disabled leaves legacy behavior
untouched, Auth enabled refuses to serve on an unreachable or unmigrated
database, resources are created and disposed exactly once, and no failure path
leaks a credential.

No live PostgreSQL server is required. Connectivity failure is exercised against
a closed local port, and the migration check is injected, so these tests stay
deterministic and offline (Todo 3 owns the real-database migration suite).
"""

from pathlib import Path
from typing import NotRequired, TypedDict, Unpack, cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.auth.composition import (
    AuthComposition,
    AuthDatabaseUnavailableError,
    AuthMigrationStateError,
    AuthStartupError,
    describe_database_target,
    verify_auth_schema,
)
from src.auth.infrastructure.migrations import expected_auth_head
from src.auth.settings import AuthSettings
from src.main import app

DB_PASSWORD = "sup3rs3cr3t_db_pw"
# Port 1 is reserved and never listening, so connect fails fast without waiting
# on a DNS or network timeout.
UNREACHABLE_URL = f"postgresql+asyncpg://p150_auth:{DB_PASSWORD}@127.0.0.1:1/p150_auth"

STRONG_SECRET = "u7Qx2Lm9Vt4Zb8Nr6Kc3Ye5Ws1Ad0Fg7Hj2Pl9Sn4Bv6Mz8Xq"
ANOTHER_STRONG_SECRET = "Rk3Wp8Ty1Uo6Ia4Ed9Qz2Cx7Vb5Nm0Lj3Hg8Fd6Sa1Pw4Ry7Tn"


class AuthSettingsOverrides(TypedDict):
    """Typed values permitted by the Auth lifespan settings builder."""

    app_env: NotRequired[str]
    database_url: NotRequired[str]
    jwt_signing_key: NotRequired[str]
    csrf_secret: NotRequired[str]
    cors_origins: NotRequired[str]
    frontend_origin: NotRequired[str]


def enabled_settings(**overrides: Unpack[AuthSettingsOverrides]) -> AuthSettings:
    values: AuthSettingsOverrides = {
        "app_env": "development",
        "database_url": UNREACHABLE_URL,
        "jwt_signing_key": STRONG_SECRET,
        "csrf_secret": ANOTHER_STRONG_SECRET,
        "cors_origins": "http://localhost:3000",
        "frontend_origin": "http://localhost:3000",
    }
    return AuthSettings(_env_file=None, enabled=True, **(values | overrides))


def disabled_settings() -> AuthSettings:
    return AuthSettings(_env_file=None, enabled=False)


class RecordingVerifier:
    """Schema verifier stub that records calls instead of querying."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    async def __call__(self, engine: AsyncEngine, target: str) -> None:
        self.calls.append(target)
        if self.error is not None:
            raise self.error


class TestDisabledAuthIsANoOp:
    @pytest.mark.asyncio
    async def test_start_creates_no_resources(self) -> None:
        composition = AuthComposition(disabled_settings())
        await composition.start()
        assert composition.enabled is False
        with pytest.raises(AuthStartupError):
            _ = composition.resources

    @pytest.mark.asyncio
    async def test_shutdown_without_start_is_safe(self) -> None:
        composition = AuthComposition(disabled_settings())
        await composition.shutdown()
        await composition.shutdown()

    @pytest.mark.asyncio
    async def test_schema_check_is_never_invoked(self) -> None:
        verifier = RecordingVerifier()
        await AuthComposition(disabled_settings(), verify_schema=verifier).start()
        assert verifier.calls == []


class TestLegacyApplicationRemainsUnchanged:
    """The default test environment has Auth disabled, so legacy routes must work."""

    @pytest.mark.asyncio
    async def test_health_still_serves_through_full_lifespan(self) -> None:
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_lifespan_exposes_auth_composition_on_app_state(self) -> None:
        async with app.router.lifespan_context(app):
            assert isinstance(app.state.auth, AuthComposition)


class TestUnreachableDatabaseFailsFast:
    @pytest.mark.asyncio
    async def test_start_raises_database_unavailable(self) -> None:
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier())
        with pytest.raises(AuthDatabaseUnavailableError):
            await composition.start()

    @pytest.mark.asyncio
    async def test_error_identifies_host_without_leaking_password(self) -> None:
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier())
        with pytest.raises(AuthDatabaseUnavailableError) as exc:
            await composition.start()
        message = str(exc.value)
        assert "127.0.0.1:1/p150_auth" in message
        assert DB_PASSWORD not in message
        assert "p150_auth:" not in message

    @pytest.mark.asyncio
    async def test_chained_cause_is_suppressed_so_url_cannot_surface(self) -> None:
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier())
        with pytest.raises(AuthDatabaseUnavailableError) as exc:
            await composition.start()
        assert exc.value.__cause__ is None

    @pytest.mark.asyncio
    async def test_failed_start_leaves_no_resources(self) -> None:
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier())
        with pytest.raises(AuthDatabaseUnavailableError):
            await composition.start()
        with pytest.raises(AuthStartupError):
            _ = composition.resources

    @pytest.mark.asyncio
    async def test_schema_check_is_skipped_when_unreachable(self) -> None:
        verifier = RecordingVerifier()
        with pytest.raises(AuthDatabaseUnavailableError):
            await AuthComposition(enabled_settings(), verify_schema=verifier).start()
        assert verifier.calls == []


class TestMigrationStateGate:
    @pytest.mark.asyncio
    async def test_unmigrated_database_blocks_startup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        composition = AuthComposition(
            enabled_settings(),
            verify_schema=RecordingVerifier(AuthMigrationStateError("no revision applied")),
        )
        # Connectivity must pass so the migration gate is the failing step.
        monkeypatch.setattr(composition, "_verify_connectivity", _noop_connectivity)
        with pytest.raises(AuthMigrationStateError):
            await composition.start()

    @pytest.mark.asyncio
    async def test_migration_failure_disposes_the_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        composition = AuthComposition(
            enabled_settings(),
            verify_schema=RecordingVerifier(AuthMigrationStateError("no revision applied")),
        )
        monkeypatch.setattr(composition, "_verify_connectivity", _noop_connectivity)
        with pytest.raises(AuthMigrationStateError):
            await composition.start()
        with pytest.raises(AuthStartupError):
            _ = composition.resources


class TestSuccessfulStartupOwnsResourcesOnce:
    @pytest.mark.asyncio
    async def test_resources_are_available_after_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier())
        monkeypatch.setattr(composition, "_verify_connectivity", _noop_connectivity)
        await composition.start()
        try:
            resources = composition.resources
            assert resources.engine is not None
            assert resources.session_factory is not None
        finally:
            await composition.shutdown()

    @pytest.mark.asyncio
    async def test_double_start_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier())
        monkeypatch.setattr(composition, "_verify_connectivity", _noop_connectivity)
        await composition.start()
        try:
            with pytest.raises(AuthStartupError):
                await composition.start()
        finally:
            await composition.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_disposes_and_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier())
        monkeypatch.setattr(composition, "_verify_connectivity", _noop_connectivity)
        await composition.start()
        engine = composition.resources.engine
        await composition.shutdown()
        await composition.shutdown()
        with pytest.raises(AuthStartupError):
            _ = composition.resources
        # A disposed engine's pool is replaced, so checked-out connections are zero.
        assert engine.pool.checkedout() == 0

    @pytest.mark.asyncio
    async def test_schema_verifier_receives_redacted_target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        verifier = RecordingVerifier()
        composition = AuthComposition(enabled_settings(), verify_schema=verifier)
        monkeypatch.setattr(composition, "_verify_connectivity", _noop_connectivity)
        await composition.start()
        try:
            assert verifier.calls == ["127.0.0.1:1/p150_auth"]
            assert DB_PASSWORD not in verifier.calls[0]
        finally:
            await composition.shutdown()


class _StubResult:
    """Stands in for a `CursorResult` over the `alembic_version` rows."""

    def __init__(self, rows: list[tuple[str]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[str]]:
        return self._rows


class _RaisingConnection:
    """Async connection stub whose query raises a chosen SQLAlchemy error."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def __aenter__(self) -> "_RaisingConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> _StubResult:
        raise self.error


class _RevisionConnection(_RaisingConnection):
    """Async connection stub returning chosen `alembic_version` rows."""

    def __init__(self, revisions: list[str]) -> None:
        super().__init__(RuntimeError("unused"))
        self._revisions = revisions

    async def execute(self, *args: object, **kwargs: object) -> _StubResult:
        return _StubResult([(revision,) for revision in self._revisions])


class _StubEngine:
    """Minimal engine stub exposing only what `verify_auth_schema` uses."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def connect(self) -> _RaisingConnection:
        return _RaisingConnection(self.error)


class _RevisionEngine(_StubEngine):
    """Engine stub whose connection reports a fixed set of applied revisions."""

    def __init__(self, revisions: list[str]) -> None:
        super().__init__(RuntimeError("unused"))
        self._revisions = revisions

    def connect(self) -> _RaisingConnection:
        return _RevisionConnection(self._revisions)


def _as_engine(stub: "_StubEngine") -> AsyncEngine:
    """Present a stub as an `AsyncEngine`.

    `verify_auth_schema` only calls `connect()`, so a stub satisfies it at
    runtime. The cast states that narrowing explicitly instead of suppressing the
    type error.
    """
    return cast(AsyncEngine, stub)


def _programming_error() -> ProgrammingError:
    """The error asyncpg raises when `alembic_version` does not exist."""
    return ProgrammingError(
        "SELECT version_num FROM alembic_version LIMIT 1",
        {},
        Exception('relation "alembic_version" does not exist'),
    )


class TestUnmigratedDatabaseIsNotReportedAsUnavailable:
    """Regression: a missing `alembic_version` table is a migration problem.

    Verified against a real PostgreSQL 16 container: an empty Auth database made
    `verify_auth_schema` raise `ProgrammingError`, which the startup handler
    reported as "database unavailable". That sends the operator to debug
    connectivity when the actual fix is running migrations.
    """

    @pytest.mark.asyncio
    async def test_missing_version_table_raises_migration_error(self) -> None:
        with pytest.raises(AuthMigrationStateError):
            await verify_auth_schema(_as_engine(_StubEngine(_programming_error())), "db-host/p150_auth")

    @pytest.mark.asyncio
    async def test_migration_error_names_the_upgrade_command(self) -> None:
        with pytest.raises(AuthMigrationStateError) as exc:
            await verify_auth_schema(_as_engine(_StubEngine(_programming_error())), "db-host/p150_auth")
        assert "alembic -c alembic-auth.ini upgrade head" in str(exc.value)

    @pytest.mark.asyncio
    async def test_missing_table_is_not_classified_as_unavailable(self) -> None:
        with pytest.raises(AuthMigrationStateError) as exc:
            await verify_auth_schema(_as_engine(_StubEngine(_programming_error())), "db-host/p150_auth")
        assert not isinstance(exc.value, AuthDatabaseUnavailableError)

    @pytest.mark.asyncio
    async def test_empty_version_table_raises_migration_error(self) -> None:
        with pytest.raises(AuthMigrationStateError):
            await verify_auth_schema(_as_engine(_RevisionEngine([])), "db-host/p150_auth")

    @pytest.mark.asyncio
    async def test_start_surfaces_migration_error_not_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The startup handler must not re-classify the migration error."""
        composition = AuthComposition(
            enabled_settings(),
            verify_schema=RecordingVerifier(AuthMigrationStateError("no revision applied")),
        )
        monkeypatch.setattr(composition, "_verify_connectivity", _noop_connectivity)
        with pytest.raises(AuthMigrationStateError):
            await composition.start()

    @pytest.mark.asyncio
    async def test_genuine_connection_error_still_reports_unavailable(self) -> None:
        """A real transport failure must keep its own classification."""
        operational = OperationalError("SELECT 1", {}, Exception("connection refused"))
        composition = AuthComposition(enabled_settings(), verify_schema=RecordingVerifier(operational))
        with pytest.raises(AuthDatabaseUnavailableError):
            await composition.start()


class TestExpectedHeadIsEnforced:
    """A revision that is not the expected head must fail startup.

    Todo 1 could only assert that *some* revision was applied, because no Auth
    history existed to compare against. With the history in place, a database
    stuck on an older revision has a schema that does not match the models, and
    letting it boot defers the failure to a live request.
    """

    @pytest.mark.asyncio
    async def test_expected_head_passes(self) -> None:
        head = expected_auth_head()
        await verify_auth_schema(_as_engine(_RevisionEngine([head])), "db-host/p150_auth")

    @pytest.mark.asyncio
    async def test_stale_revision_raises_migration_error(self) -> None:
        with pytest.raises(AuthMigrationStateError):
            await verify_auth_schema(_as_engine(_RevisionEngine(["0000deadbeef"])), "db-host/p150_auth")

    @pytest.mark.asyncio
    async def test_mismatch_message_names_both_revisions(self) -> None:
        with pytest.raises(AuthMigrationStateError) as exc:
            await verify_auth_schema(_as_engine(_RevisionEngine(["0000deadbeef"])), "db-host/p150_auth")
        message = str(exc.value)
        assert "0000deadbeef" in message
        assert expected_auth_head() in message
        assert "alembic -c alembic-auth.ini upgrade head" in message

    @pytest.mark.asyncio
    async def test_stale_revision_is_not_classified_as_unavailable(self) -> None:
        with pytest.raises(AuthMigrationStateError) as exc:
            await verify_auth_schema(_as_engine(_RevisionEngine(["0000deadbeef"])), "db-host/p150_auth")
        assert not isinstance(exc.value, AuthDatabaseUnavailableError)

    @pytest.mark.asyncio
    async def test_branched_history_rows_are_rejected(self) -> None:
        """Two rows in `alembic_version` must not pass by reading only the first."""
        head = expected_auth_head()
        with pytest.raises(AuthMigrationStateError):
            await verify_auth_schema(_as_engine(_RevisionEngine([head, "0000deadbeef"])), "db-host/p150_auth")

    def test_head_is_read_from_the_auth_history(self) -> None:
        """The expected head is resolved from `alembic-auth.ini`, not hardcoded."""
        head = expected_auth_head()
        revisions = (Path("migrations/auth/versions")).glob("*.py")
        assert head in {path.name.split("_", 1)[0] for path in revisions}


class TestDatabaseTargetRedaction:
    def test_describes_host_port_and_name_only(self) -> None:
        assert describe_database_target(UNREACHABLE_URL) == "127.0.0.1:1/p150_auth"

    def test_omits_user_and_password(self) -> None:
        described = describe_database_target(UNREACHABLE_URL)
        assert DB_PASSWORD not in described
        assert "p150_auth:" not in described

    def test_handles_url_without_port_or_name(self) -> None:
        described = describe_database_target("postgresql+asyncpg://user:pw@db-host")
        assert described == "db-host/<unknown database>"
        assert "pw" not in described.replace("db-host", "")


async def _noop_connectivity(engine: AsyncEngine, target: str) -> None:
    """Stand in for a reachable database without opening a connection."""
    return None
