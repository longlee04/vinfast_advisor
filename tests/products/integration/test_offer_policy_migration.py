"""Acceptance tests for the ``e5f6a7b8c9d0`` offer-policy migration."""

from subprocess import CompletedProcess

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.products.integration.conftest import run_product_alembic

POLICY_TABLES = {"offer_adjustment_policies", "offer_adjustment_log"}
POLICY_COLUMNS = {
    "promotion_type",
    "adjust_min_vnd",
    "adjust_max_vnd",
    "adjust_min_percent",
    "adjust_max_percent",
    "financing_months_min",
    "financing_months_max",
    "financing_support_max_vnd",
    "gift_value_max_vnd",
    "allowed_gift_codes",
    "registration_support_max_vnd",
    "other_max_vnd",
}
LOG_COLUMNS = {
    "id",
    "review_id",
    "advisor_id",
    "promotion_code",
    "adjustment_type",
    "old_value",
    "new_value",
    "reason",
    "created_at",
}
PREVIOUS_REVISION = "a1b2c3d4e5f6"
NEW_REVISION = "e5f6a7b8c9d0"
PRE_GENERALIZED_REVISION = "e5f6a7b8c9d0"
GENERALIZED_REVISION = "e6f7a8b9c0d1"


def _assert_alembic_succeeds(completed: CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stderr


async def _product_revision(database_url: str) -> str | None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            version_table_exists = await connection.scalar(
                text("SELECT to_regclass('public.alembic_version_products') IS NOT NULL")
            )
            if not version_table_exists:
                return None
            return await connection.scalar(text("SELECT version_num FROM alembic_version_products"))
    finally:
        await engine.dispose()


async def _table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    finally:
        await engine.dispose()


async def _column_names(database_url: str, table_name: str) -> set[str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync: {column["name"] for column in inspect(sync).get_columns(table_name)}
            )
    finally:
        await engine.dispose()


async def _seed_policy_count(database_url: str) -> int:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT count(*) FROM offer_adjustment_policies"))
    finally:
        await engine.dispose()


async def _prepare_previous_revision(database_url: str) -> None:
    completed = run_product_alembic(database_url, "upgrade", PREVIOUS_REVISION)
    _assert_alembic_succeeds(completed)
    assert await _product_revision(database_url) == PREVIOUS_REVISION


def _restore_product_head(database_url: str) -> None:
    _assert_alembic_succeeds(run_product_alembic(database_url, "upgrade", "head"))


@pytest.mark.asyncio
async def test_upgrade_creates_tables_and_seed(product_transition_database_url: str) -> None:
    # Given
    await _prepare_previous_revision(product_transition_database_url)

    try:
        # When
        completed = run_product_alembic(product_transition_database_url, "upgrade", NEW_REVISION)

        # Then
        _assert_alembic_succeeds(completed)
        assert await _product_revision(product_transition_database_url) == NEW_REVISION
        assert POLICY_TABLES <= await _table_names(product_transition_database_url)
        assert POLICY_COLUMNS <= await _column_names(product_transition_database_url, "offer_adjustment_policies")
        assert LOG_COLUMNS <= await _column_names(product_transition_database_url, "offer_adjustment_log")
        assert await _seed_policy_count(product_transition_database_url) == 6
    finally:
        _restore_product_head(product_transition_database_url)


@pytest.mark.asyncio
async def test_downgrade_removes_tables_and_gift_group(product_transition_database_url: str) -> None:
    # Given
    _assert_alembic_succeeds(run_product_alembic(product_transition_database_url, "upgrade", NEW_REVISION))

    try:
        # When
        completed = run_product_alembic(product_transition_database_url, "downgrade", PREVIOUS_REVISION)

        # Then
        _assert_alembic_succeeds(completed)
        assert await _product_revision(product_transition_database_url) == PREVIOUS_REVISION
        assert POLICY_TABLES.isdisjoint(await _table_names(product_transition_database_url))
    finally:
        _restore_product_head(product_transition_database_url)


@pytest.mark.asyncio
async def test_generalized_audit_source_upgrade_backfills_and_enforces_contract(
    product_transition_database_url: str,
) -> None:
    # Given
    _assert_alembic_succeeds(run_product_alembic(product_transition_database_url, "upgrade", PRE_GENERALIZED_REVISION))
    review_id = "11111111-1111-1111-1111-111111111111"
    engine = create_async_engine(product_transition_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO offer_adjustment_log "
                    "(id, review_id, advisor_id, promotion_code, adjustment_type, created_at) "
                    "VALUES (gen_random_uuid(), :review_id, 'advisor-a', 'FIN-1', 'VND', NOW())"
                ),
                {"review_id": review_id},
            )

        # When
        completed = run_product_alembic(product_transition_database_url, "upgrade", GENERALIZED_REVISION)

        # Then
        _assert_alembic_succeeds(completed)
        async with engine.begin() as connection:
            row = (
                await connection.execute(
                    text("SELECT review_id::text, source_kind, source_id::text FROM offer_adjustment_log")
                )
            ).one()
            assert row == (review_id, "CONTENT_REVIEW", review_id)
            with pytest.raises(IntegrityError):
                await connection.execute(
                    text(
                        "INSERT INTO offer_adjustment_log "
                        "(id, review_id, source_kind, source_id, advisor_id, promotion_code, "
                        "adjustment_type, created_at) VALUES "
                        "(gen_random_uuid(), NULL, 'CONTENT_REVIEW', gen_random_uuid(), "
                        "'advisor-a', 'FIN-2', 'VND', NOW())"
                    )
                )
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM offer_adjustment_log WHERE review_id = :review_id"),
                {"review_id": review_id},
            )
    finally:
        await engine.dispose()
        _restore_product_head(product_transition_database_url)


@pytest.mark.asyncio
async def test_generalized_audit_source_downgrade_deletes_signal_rows(
    product_transition_database_url: str,
) -> None:
    # Given
    _assert_alembic_succeeds(run_product_alembic(product_transition_database_url, "upgrade", GENERALIZED_REVISION))
    engine = create_async_engine(product_transition_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO offer_adjustment_log "
                    "(id, review_id, source_kind, source_id, advisor_id, promotion_code, "
                    "adjustment_type, created_at) VALUES "
                    "(gen_random_uuid(), NULL, 'BOTTLENECK_SIGNAL', gen_random_uuid(), "
                    "'advisor-a', 'FIN-1', 'VND', NOW())"
                )
            )

        # When
        completed = run_product_alembic(product_transition_database_url, "downgrade", PRE_GENERALIZED_REVISION)

        # Then
        _assert_alembic_succeeds(completed)
        assert {"source_kind", "source_id"}.isdisjoint(
            await _column_names(product_transition_database_url, "offer_adjustment_log")
        )
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM offer_adjustment_log")) == 0
    finally:
        await engine.dispose()
        _restore_product_head(product_transition_database_url)


@pytest.mark.asyncio
async def test_seed_bounds_are_sane(product_transition_database_url: str) -> None:
    """Seed defaults must keep min < max and avoid negative/absurd values."""
    # Given
    _assert_alembic_succeeds(run_product_alembic(product_transition_database_url, "upgrade", "head"))

    engine = create_async_engine(product_transition_database_url)
    try:
        async with engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT promotion_type, adjust_min_vnd, adjust_max_vnd, "
                            "adjust_min_percent, adjust_max_percent, financing_months_min, "
                            "financing_months_max, financing_support_max_vnd "
                            "FROM offer_adjustment_policies"
                        )
                    )
                )
                .mappings()
                .all()
            )

        by_type = {row["promotion_type"]: row for row in rows}
        assert set(by_type) == {
            "FIXED_DISCOUNT",
            "PERCENT_DISCOUNT",
            "GIFT",
            "FINANCING",
            "REGISTRATION_SUPPORT",
            "OTHER",
        }

        fixed = by_type["FIXED_DISCOUNT"]
        assert fixed["adjust_min_vnd"] == 0 and fixed["adjust_max_vnd"] == 10_000_000
        assert fixed["adjust_min_vnd"] < fixed["adjust_max_vnd"]

        percent = by_type["PERCENT_DISCOUNT"]
        assert percent["adjust_min_percent"] == 0 and percent["adjust_max_percent"] == 5
        assert percent["adjust_min_percent"] < percent["adjust_max_percent"]

        financing = by_type["FINANCING"]
        assert financing["financing_months_min"] == 6 and financing["financing_months_max"] == 36
        assert financing["financing_months_min"] < financing["financing_months_max"]
        assert financing["financing_support_max_vnd"] == 20_000_000

        for row in rows:
            for key in (
                "adjust_min_vnd",
                "adjust_max_vnd",
                "adjust_min_percent",
                "adjust_max_percent",
                "financing_months_min",
                "financing_months_max",
                "financing_support_max_vnd",
            ):
                value = row[key]
                assert value is None or value >= 0, f"{row['promotion_type']}.{key} is negative"
    finally:
        await engine.dispose()
