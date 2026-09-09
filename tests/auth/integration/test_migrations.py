"""Auth migration tests against a real PostgreSQL server.

Four properties are checked, each of which has a way of breaking silently:

* The history has exactly one head and applies cleanly to an empty database.
* `downgrade base` then `upgrade head` succeeds, so a rollback is a real option
  rather than a documented hope.
* The applied schema matches the models. Autogenerate is asked whether it would
  emit anything; a non-empty answer means the checked-in revision has drifted.
* Auth migrations touch only `auth_*` tables. Auth shares a database process with
  the legacy path, and an Auth revision dropping a legacy table would be
  discovered far too late.
"""

import pytest
import pytest_asyncio
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.auth.composition import AuthMigrationStateError, verify_auth_schema
from src.auth.infrastructure.migrations import expected_auth_head
from src.auth.infrastructure.models import AuthBase
from tests.auth.integration.conftest import run_alembic

LEGACY_TABLE = "legacy_probe_table"

EXPECTED_AUTH_TABLES = {
    "auth_users",
    "auth_bootstrap_admin_claims",
    "auth_refresh_tokens",
    "auth_one_time_tokens",
    "auth_rate_limit_counters",
    "auth_security_events",
}


@pytest_asyncio.fixture
async def migrated(engine: AsyncEngine) -> AsyncEngine:
    """The engine, guaranteed to be at head.

    Tests in this module move the revision pointer, so each one starts from a
    known position rather than from whatever the previous test left behind.
    """
    completed = run_alembic("upgrade", "head")
    assert completed.returncode == 0, completed.stderr
    return engine


class TestMigrationHistory:
    def test_history_has_exactly_one_head(self) -> None:
        """A branched history makes "migrated" ambiguous at startup."""
        completed = run_alembic("heads")
        assert completed.returncode == 0, completed.stderr
        heads = [line for line in completed.stdout.splitlines() if line.strip()]
        assert len(heads) == 1, completed.stdout
        assert expected_auth_head() in heads[0]

    @pytest.mark.asyncio
    async def test_upgrade_creates_every_auth_table(self, migrated: AsyncEngine) -> None:
        tables = await _table_names(migrated)
        assert EXPECTED_AUTH_TABLES <= tables

    @pytest.mark.asyncio
    async def test_current_revision_is_head(self, migrated: AsyncEngine) -> None:
        async with migrated.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == expected_auth_head()

    @pytest.mark.asyncio
    async def test_upgrade_is_idempotent(self, migrated: AsyncEngine) -> None:
        """Re-running upgrade must be a no-op, not an error."""
        completed = run_alembic("upgrade", "head")
        assert completed.returncode == 0, completed.stderr
        tables = await _table_names(migrated)
        assert EXPECTED_AUTH_TABLES <= tables

    @pytest.mark.asyncio
    async def test_downgrade_then_reupgrade_succeeds(self, migrated: AsyncEngine) -> None:
        down = run_alembic("downgrade", "base")
        assert down.returncode == 0, down.stderr
        after_downgrade = await _table_names(migrated)
        assert not (EXPECTED_AUTH_TABLES & after_downgrade)

        up = run_alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr
        assert EXPECTED_AUTH_TABLES <= await _table_names(migrated)


class TestSchemaMatchesModels:
    @pytest.mark.asyncio
    async def test_autogenerate_detects_no_drift(self, migrated: AsyncEngine) -> None:
        """The checked-in revision must fully describe the current models."""
        async with migrated.connect() as connection:
            diff = await connection.run_sync(_compare_to_models)
        assert diff == [], f"schema drift detected: {diff}"

    @pytest.mark.asyncio
    async def test_email_uniqueness_is_enforced_by_the_database(self, migrated: AsyncEngine) -> None:
        """Uniqueness lives in the schema, not only in application code."""
        async with migrated.connect() as connection:
            indexes = await connection.run_sync(lambda sync: inspect(sync).get_indexes("auth_users"))
            constraints = await connection.run_sync(lambda sync: inspect(sync).get_unique_constraints("auth_users"))
        unique_on_email = any(c["column_names"] == ["email"] for c in constraints) or any(
            index.get("unique") and index["column_names"] == ["email"] for index in indexes
        )
        assert unique_on_email


class TestLegacyBoundary:
    def test_auth_metadata_contains_only_auth_tables(self) -> None:
        """`AuthBase.metadata` is what autogenerate compares against."""
        assert all(name.startswith("auth_") for name in AuthBase.metadata.tables)

    @pytest.mark.asyncio
    async def test_downgrade_leaves_a_non_auth_table_untouched(self, migrated: AsyncEngine) -> None:
        """A full downgrade must not reach outside the Auth namespace."""
        async with migrated.begin() as connection:
            await connection.execute(text(f"CREATE TABLE IF NOT EXISTS {LEGACY_TABLE} (id integer)"))
            await connection.execute(text(f"INSERT INTO {LEGACY_TABLE} (id) VALUES (1)"))
        try:
            down = run_alembic("downgrade", "base")
            assert down.returncode == 0, down.stderr
            async with migrated.connect() as connection:
                rows = await connection.scalar(text(f"SELECT count(*) FROM {LEGACY_TABLE}"))
            assert rows == 1
        finally:
            async with migrated.begin() as connection:
                await connection.execute(text(f"DROP TABLE IF EXISTS {LEGACY_TABLE}"))
            up = run_alembic("upgrade", "head")
            assert up.returncode == 0, up.stderr

    @pytest.mark.asyncio
    async def test_autogenerate_never_proposes_dropping_a_legacy_table(self, migrated: AsyncEngine) -> None:
        """An unrelated table in the same database must not appear as a diff.

        This is the concrete risk of a shared declarative base: autogenerate would
        see a table it does not know about and emit `drop_table`.
        """
        async with migrated.begin() as connection:
            await connection.execute(text(f"CREATE TABLE IF NOT EXISTS {LEGACY_TABLE} (id integer)"))
        try:
            async with migrated.connect() as connection:
                diff = await connection.run_sync(_compare_to_models)
            assert LEGACY_TABLE not in repr(diff)
        finally:
            async with migrated.begin() as connection:
                await connection.execute(text(f"DROP TABLE IF EXISTS {LEGACY_TABLE}"))


class TestStartupRejectsAStaleRevision:
    """Startup must compare the applied revision against the expected head.

    Todo 1 could only assert that *some* revision existed, because there was no
    Auth history to compare against. A database left on an older revision would
    therefore boot, and the schema mismatch would surface as an undefined-column
    error on a live request instead of at startup.
    """

    @pytest.mark.asyncio
    async def test_head_revision_passes_verification(self, migrated: AsyncEngine) -> None:
        await verify_auth_schema(migrated, "test-db/p150_auth")

    @pytest.mark.asyncio
    async def test_stamped_older_revision_fails_verification(self, migrated: AsyncEngine) -> None:
        stale = "0000stalerev0"
        async with migrated.begin() as connection:
            await connection.execute(text("UPDATE alembic_version SET version_num = :revision"), {"revision": stale})
        try:
            with pytest.raises(AuthMigrationStateError) as exc:
                await verify_auth_schema(migrated, "test-db/p150_auth")
            message = str(exc.value)
            assert stale in message
            assert expected_auth_head() in message
        finally:
            async with migrated.begin() as connection:
                await connection.execute(
                    text("UPDATE alembic_version SET version_num = :revision"),
                    {"revision": expected_auth_head()},
                )

    @pytest.mark.asyncio
    async def test_unmigrated_database_reports_migration_state(self, migrated: AsyncEngine) -> None:
        """The regression that only a real server exposed: empty is not unreachable."""
        down = run_alembic("downgrade", "base")
        assert down.returncode == 0, down.stderr
        async with migrated.begin() as connection:
            await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        try:
            with pytest.raises(AuthMigrationStateError):
                await verify_auth_schema(migrated, "test-db/p150_auth")
        finally:
            up = run_alembic("upgrade", "head")
            assert up.returncode == 0, up.stderr


def _compare_to_models(connection: Connection) -> list[object]:
    """Return the diff autogenerate would emit for `AuthBase.metadata`."""
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "compare_server_default": True,
            "target_metadata": AuthBase.metadata,
            # Without this, every table in the database that Auth does not own
            # would be reported as a removal.
            "include_object": _is_auth_object,
        },
    )
    return list(compare_metadata(context, AuthBase.metadata))


def _is_auth_object(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object) -> bool:
    if type_ == "table":
        return bool(name and name.startswith("auth_"))
    return True


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    return set(names)
