"""Safety contract for disposable PostgreSQL integration databases."""

from urllib.parse import parse_qs, urlsplit

import pytest

from tests.support.minio_test_bucket import (
    UnsafeTestBucketError,
    assert_disposable_bucket_name,
)
from tests.support.postgres_test_database import (
    UnsafeTestDatabaseError,
    assert_disposable_database_name,
    assert_disposable_database_url,
    database_name_from_url,
    database_url_with_name,
    generate_test_database_name,
)

DOCUMENT_PREFIX = "p150_document_test_"
IMAGE_PREFIX = "p150_image_test_"
ADMIN_URL = (
    "postgresql+asyncpg://test_user:test_password@localhost:5432/postgres"
    "?ssl=disable&application_name=p150-tests"
)


@pytest.mark.parametrize(
    "database_name",
    [
        "p150_auth",
        "p150_dev",
        "p150_staging",
        "postgres",
        "template0",
        "template1",
        "p150_production",
    ],
)
def test_rejects_protected_database_names(database_name: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_disposable_database_name(database_name, expected_prefix=DOCUMENT_PREFIX)


def test_rejects_database_from_another_module() -> None:
    database_name = generate_test_database_name(IMAGE_PREFIX)

    with pytest.raises(UnsafeTestDatabaseError, match="prefix"):
        assert_disposable_database_name(database_name, expected_prefix=DOCUMENT_PREFIX)


@pytest.mark.parametrize(
    "database_name",
    [
        "p150_document_test_not-a-uuid",
        "p150_document_test_abc",
        "p150_document_test_0123456789abcdef0123456789abcdeg",
    ],
)
def test_rejects_database_without_generated_uuid(database_name: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_disposable_database_name(database_name, expected_prefix=DOCUMENT_PREFIX)


def test_accepts_generated_database_name() -> None:
    database_name = generate_test_database_name(DOCUMENT_PREFIX)

    assert_disposable_database_name(
        database_name,
        expected_prefix=DOCUMENT_PREFIX,
        owned_database_name=database_name,
    )

    assert len(database_name) <= 63
    assert database_name.replace("_", "").isalnum()


def test_refuses_database_not_owned_by_fixture() -> None:
    database_name = generate_test_database_name(DOCUMENT_PREFIX)
    different_name = generate_test_database_name(DOCUMENT_PREFIX)

    with pytest.raises(UnsafeTestDatabaseError, match="not owned"):
        assert_disposable_database_name(
            database_name,
            expected_prefix=DOCUMENT_PREFIX,
            owned_database_name=different_name,
        )


def test_replaces_only_database_component_of_url() -> None:
    database_name = generate_test_database_name(DOCUMENT_PREFIX)

    replaced = database_url_with_name(ADMIN_URL, database_name)
    parsed = urlsplit(replaced)

    assert parsed.scheme == "postgresql+asyncpg"
    assert parsed.hostname == "localhost"
    assert parsed.port == 5432
    assert parsed.username == "test_user"
    assert parsed.password == "test_password"
    assert parsed.path == f"/{database_name}"
    assert parse_qs(parsed.query) == {
        "application_name": ["p150-tests"],
        "ssl": ["disable"],
    }


def test_disposable_url_validation_returns_database_name() -> None:
    database_name = generate_test_database_name(DOCUMENT_PREFIX)
    database_url = database_url_with_name(ADMIN_URL, database_name)

    assert database_name_from_url(database_url) == database_name
    assert (
        assert_disposable_database_url(
            database_url,
            expected_prefix=DOCUMENT_PREFIX,
            owned_database_name=database_name,
        )
        == database_name
    )


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite+aiosqlite:///test.db",
        "postgresql+asyncpg:///missing-host",
        "not-a-url",
    ],
)
def test_rejects_invalid_or_non_postgres_urls(database_url: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        database_name_from_url(database_url)


@pytest.mark.parametrize("bucket_name", ["documents", "images", "production-documents"])
def test_rejects_non_test_minio_buckets(bucket_name: str) -> None:
    with pytest.raises(UnsafeTestBucketError):
        assert_disposable_bucket_name(bucket_name, expected_prefix="document-test-")


def test_accepts_only_the_fixture_owned_minio_bucket() -> None:
    bucket_name = "image-test-0123456789abcdef0123456789abcdef"

    assert_disposable_bucket_name(
        bucket_name,
        expected_prefix="image-test-",
        owned_bucket_name=bucket_name,
    )

    with pytest.raises(UnsafeTestBucketError, match="not owned"):
        assert_disposable_bucket_name(
            bucket_name,
            expected_prefix="image-test-",
            owned_bucket_name="image-test-fedcba9876543210fedcba9876543210",
        )
