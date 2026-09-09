"""Apply Document and Product migrations to a disposable test database."""

import os
import subprocess
import sys
from pathlib import Path

from tests.support.postgres_test_database import TemporaryPostgresDatabase

DOCUMENT_BASE_REVISION = "4d0cument0001"


def run_document_alembic(
    database: TemporaryPostgresDatabase,
    repository_root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run Document Alembic against a fixture-owned database."""
    return _run_alembic(
        database,
        repository_root,
        configuration="alembic-document.ini",
        environment_variable="DOCUMENT_DATABASE_URL",
        arguments=arguments,
    )


def apply_document_test_schema(
    database: TemporaryPostgresDatabase,
    repository_root: Path,
) -> None:
    """Apply Document/Product migrations in their required dependency order."""
    document_base = run_document_alembic(
        database,
        repository_root,
        "upgrade",
        DOCUMENT_BASE_REVISION,
    )
    assert document_base.returncode == 0, document_base.stderr
    products = _run_alembic(
        database,
        repository_root,
        configuration="alembic-products.ini",
        environment_variable="PRODUCT_DATABASE_URL",
        arguments=("upgrade", "head"),
    )
    assert products.returncode == 0, products.stderr
    document_head = run_document_alembic(database, repository_root, "upgrade", "head")
    assert document_head.returncode == 0, document_head.stderr


def prepare_document_migration_database(
    database: TemporaryPostgresDatabase,
    repository_root: Path,
) -> None:
    """Install Product prerequisites while leaving Document at migration base."""
    document_base = run_document_alembic(
        database,
        repository_root,
        "upgrade",
        DOCUMENT_BASE_REVISION,
    )
    assert document_base.returncode == 0, document_base.stderr
    products = _run_alembic(
        database,
        repository_root,
        configuration="alembic-products.ini",
        environment_variable="PRODUCT_DATABASE_URL",
        arguments=("upgrade", "head"),
    )
    assert products.returncode == 0, products.stderr
    reset_document = run_document_alembic(database, repository_root, "downgrade", "base")
    assert reset_document.returncode == 0, reset_document.stderr


def _run_alembic(
    database: TemporaryPostgresDatabase,
    repository_root: Path,
    *,
    configuration: str,
    environment_variable: str,
    arguments: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", configuration, *arguments],
        cwd=repository_root,
        env={**os.environ, environment_variable: database.database_url},
        capture_output=True,
        text=True,
        check=False,
    )
