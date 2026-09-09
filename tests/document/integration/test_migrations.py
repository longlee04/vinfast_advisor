"""Document migration tests against the established PostgreSQL service."""

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.document.integration.conftest import run_alembic
from tests.support.postgres_test_database import TemporaryPostgresDatabase

DOCUMENT_TABLE = "documents"
POLICY_NOTIFICATION_TABLE = "policy_notifications"
POLICY_SCOPE_TABLE = "policy_scopes"
LEGACY_TABLE = "document_legacy_probe"


@pytest_asyncio.fixture
async def engine(document_migration_database: TemporaryPostgresDatabase) -> AsyncEngine:
    created = create_async_engine(document_migration_database.database_url)
    try:
        yield created
    finally:
        await created.dispose()


class TestDocumentMigration:
    def test_history_has_one_head(
        self,
        document_migration_database: TemporaryPostgresDatabase,
    ) -> None:
        # Given
        # When
        completed = run_alembic(document_migration_database, "heads")

        # Then
        assert completed.returncode == 0, completed.stderr
        assert len([line for line in completed.stdout.splitlines() if line.strip()]) == 1

    @pytest.mark.asyncio
    async def test_upgrade_downgrade_and_reupgrade_preserve_legacy_tables(
        self,
        engine: AsyncEngine,
        document_migration_database: TemporaryPostgresDatabase,
    ) -> None:
        # Given
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {LEGACY_TABLE}"))
            await connection.execute(text(f"CREATE TABLE {LEGACY_TABLE} (id integer)"))
            await connection.execute(text(f"INSERT INTO {LEGACY_TABLE} (id) VALUES (1)"))

        # When
        upgrade = run_alembic(document_migration_database, "upgrade", "head")
        downgrade = run_alembic(document_migration_database, "downgrade", "base")
        reupgrade = run_alembic(document_migration_database, "upgrade", "head")

        # Then
        assert upgrade.returncode == 0, upgrade.stderr
        assert downgrade.returncode == 0, downgrade.stderr
        assert reupgrade.returncode == 0, reupgrade.stderr
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            rows = await connection.scalar(text(f"SELECT count(*) FROM {LEGACY_TABLE}"))
        assert DOCUMENT_TABLE in tables
        assert POLICY_NOTIFICATION_TABLE in tables
        assert POLICY_SCOPE_TABLE in tables
        assert rows == 1
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {LEGACY_TABLE}"))

    @pytest.mark.asyncio
    async def test_schema_defines_required_indexes_and_columns(
        self,
        engine: AsyncEngine,
        document_migration_database: TemporaryPostgresDatabase,
    ) -> None:
        # Given
        completed = run_alembic(document_migration_database, "upgrade", "head")
        assert completed.returncode == 0, completed.stderr

        # When
        async with engine.connect() as connection:
            indexes = await connection.run_sync(lambda sync: inspect(sync).get_indexes(DOCUMENT_TABLE))
            columns = await connection.run_sync(lambda sync: inspect(sync).get_columns(DOCUMENT_TABLE))

        # Then
        assert {"ix_documents_active", "ix_documents_created_desc"} <= {index["name"] for index in indexes}
        assert {"id", "title", "content_hash", "archived_at", "created_at", "updated_at"} <= {
            column["name"] for column in columns
        }

    @pytest.mark.asyncio
    async def test_policy_notification_schema_has_review_and_publication_contract(
        self,
        engine: AsyncEngine,
        document_migration_database: TemporaryPostgresDatabase,
    ) -> None:
        completed = run_alembic(document_migration_database, "upgrade", "head")
        assert completed.returncode == 0, completed.stderr

        async with engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync: inspect(sync).get_indexes(POLICY_NOTIFICATION_TABLE)
            )
            columns = await connection.run_sync(
                lambda sync: inspect(sync).get_columns(POLICY_NOTIFICATION_TABLE)
            )

        assert {
            "source_document_id",
            "policy_type",
            "topic",
            "facts",
            "evidence",
            "title",
            "content",
            "status",
            "published_by",
            "published_at",
        } <= {column["name"] for column in columns}
        assert {
            "ix_policy_notifications_status_published",
            "ix_policy_notifications_created",
        } <= {index["name"] for index in indexes}

    @pytest.mark.asyncio
    async def test_policy_revision_schema_separates_source_scope_and_chunk(
        self,
        engine: AsyncEngine,
        document_migration_database: TemporaryPostgresDatabase,
    ) -> None:
        completed = run_alembic(document_migration_database, "upgrade", "head")
        assert completed.returncode == 0, completed.stderr

        async with engine.connect() as connection:
            document_columns = await connection.run_sync(
                lambda sync: inspect(sync).get_columns(DOCUMENT_TABLE)
            )
            scope_columns = await connection.run_sync(
                lambda sync: inspect(sync).get_columns(POLICY_SCOPE_TABLE)
            )
            chunk_columns = await connection.run_sync(
                lambda sync: inspect(sync).get_columns("vehicle_documents")
            )

        assert {
            "source_authority",
            "source_revision",
            "source_retrieved_at",
            "supersedes_document_id",
        } <= {item["name"] for item in document_columns}
        assert {
            "policy_active_from",
            "eligibility_basis",
            "eligibility_from",
            "is_current_default",
            "resolved_vehicle_ids",
        } <= {item["name"] for item in scope_columns}
        assert "policy_scope_id" in {item["name"] for item in chunk_columns}
