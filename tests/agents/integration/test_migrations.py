"""Agent migration history and metadata parity tests."""

import re
from typing import Any, cast

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import (
    ReflectedCheckConstraint,
    ReflectedColumn,
    ReflectedForeignKeyConstraint,
    ReflectedIndex,
    ReflectedPrimaryKeyConstraint,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Table,
)

from src.agents.models import AgentBase
from tests.agents.integration.conftest import expected_agent_head, run_alembic

EXPECTED_AGENT_TABLES = {
    "conversation_sessions",
    "conversation_slots",
    "slot_ask_attempts",
    "conversation_messages",
    "conversation_summaries",
    "conversation_turn_outcomes",
    "conversation_turn_bottlenecks",
    # Wave 2 (T4) — bảng ưu đãi đã duyệt theo phiên.
    "session_offers",
    # Wave 3 (T7a) — bộ đếm chống spam `/agent/turn`, riêng của module agents.
    "agent_feature_flags",
    # Customer 360 (agent_0037/0038) — cơ hội, gắn phiên, phản hồi TVV, insight.
    "customer_opportunities",
    "session_opportunity",
    "customer360_feedback",
    "customer_insights",
    "opportunity_offers",
    "opportunity_offer_events",
    "agent_rate_limit_counters",
    "pending_feature_mentions",
    "customer_profiles",
    "out_of_scope_log",
    "agent_runs",
    "run_snapshots",
    "run_candidates",
    "run_evidence",
    "scoring_result",
    "tco_estimates",
    "review_queue",
    "quote_audit_log",
    "test_drive_bookings",
    "internal_notices",
    "notice_reads",
    "customer_advisor_assignments",
    "conversation_reassignments",
}


class TestAgentMigrationHistory:
    def test_history_has_exactly_one_head(self) -> None:
        # Given
        # When
        completed = run_alembic(None, "alembic-agent.ini", "AGENT_DATABASE_URL", "heads")

        # Then
        assert completed.returncode == 0, completed.stderr
        heads = [line for line in completed.stdout.splitlines() if line.strip()]
        assert len(heads) == 1, completed.stdout
        assert expected_agent_head() in heads[0]

    @pytest.mark.asyncio
    async def test_upgrade_creates_metadata_tables_and_funnel_view(self, migrated_engine: AsyncEngine) -> None:
        # Given
        # When
        async with migrated_engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            views = await connection.run_sync(lambda sync: set(inspect(sync).get_view_names()))

        # Then
        assert EXPECTED_AGENT_TABLES == set(AgentBase.metadata.tables)
        assert EXPECTED_AGENT_TABLES <= tables
        assert "funnel_metrics" in views

    @pytest.mark.asyncio
    async def test_live_schema_matches_agent_metadata(self, migrated_engine: AsyncEngine) -> None:
        # Given
        metadata_tables = AgentBase.metadata.tables

        # When
        async with migrated_engine.connect() as connection:
            await connection.run_sync(lambda sync: _assert_live_schema_matches_metadata(sync, metadata_tables))

        # Then
        assert set(metadata_tables) == EXPECTED_AGENT_TABLES

    @pytest.mark.asyncio
    async def test_current_revision_uses_agent_version_table(self, migrated_engine: AsyncEngine) -> None:
        # Given
        # When
        async with migrated_engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM agent_alembic_version"))

        # Then
        assert revision == expected_agent_head()

    @pytest.mark.asyncio
    async def test_agent_0025_downgrade_removes_only_signal_table_then_reupgrade_restores_it(
        self, migrated_engine: AsyncEngine, agent_database_url: str
    ) -> None:
        # Given
        async with migrated_engine.connect() as connection:
            tables_before = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))

        # When
        downgrade = run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "downgrade",
            "agent_0024",
        )
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            tables_after_downgrade = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        reupgrade = run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "upgrade",
            # Lên lại HEAD, không lên đúng `agent_0025`: chuỗi đã dài thêm, và
            # dừng ở giữa sẽ để database lệch revision cho mọi test chạy sau —
            # một ca thất bại di chuyển được, kiểu khó lần nhất.
            "head",
        )
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            tables_after_reupgrade = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))

        # Then
        assert downgrade.returncode == 0, downgrade.stderr
        # Hạ về `agent_0024` bỏ mọi bảng sinh ra từ 0025 trở đi, không chỉ bảng
        # tín hiệu. Điều test này khoá vẫn nguyên: bảng tín hiệu biến mất khi hạ
        # và quay lại khi nâng — chứ không phải "đúng một bảng bị bỏ".
        assert "conversation_turn_bottlenecks" not in tables_after_downgrade
        assert tables_after_downgrade < tables_before
        assert reupgrade.returncode == 0, reupgrade.stderr
        assert tables_before == tables_after_reupgrade

    @pytest.mark.asyncio
    async def test_pending_mention_partial_unique_index_exists(self, migrated_engine: AsyncEngine) -> None:
        async with migrated_engine.connect() as connection:
            indexes = await connection.run_sync(lambda sync: inspect(sync).get_indexes("pending_feature_mentions"))

        matching = [index for index in indexes if index["name"] == "uq_pending_feature_mentions_session_mention"]
        assert matching[0]["unique"] is True
        assert "applied_at IS NULL" in str(matching[0]["dialect_options"])

    @pytest.mark.asyncio
    async def test_agent_0007_deduplicates_only_pending_mentions(
        self, migrated_engine: AsyncEngine, agent_database_url: str
    ) -> None:
        downgrade = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0006"
        )
        assert downgrade.returncode == 0, downgrade.stderr
        session_id = "10000000-0000-0000-0000-000000000001"
        async with migrated_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO conversation_sessions (session_id, customer_id, status, started_at, last_activity_at, created_at, updated_at) VALUES (:session_id, 'customer', 'ACTIVE', now(), now(), now(), now())"
                ),
                {"session_id": session_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO pending_feature_mentions (id, session_id, raw_mention, applied_at, created_at) VALUES ('10000000-0000-0000-0000-000000000010', :session_id, 'VF 8', now(), now()), ('10000000-0000-0000-0000-000000000011', :session_id, 'VF 8', now(), now()), ('10000000-0000-0000-0000-000000000020', :session_id, 'VF 9', NULL, now()), ('10000000-0000-0000-0000-000000000021', :session_id, 'VF 9', NULL, now())"
                ),
                {"session_id": session_id},
            )
        upgrade = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "agent_0007")
        assert upgrade.returncode == 0, upgrade.stderr
        async with migrated_engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT id, raw_mention, applied_at IS NULL AS pending FROM pending_feature_mentions ORDER BY id"
                    )
                )
            ).all()
        assert [row.raw_mention for row in rows if not row.pending] == ["VF 8", "VF 8"]
        assert [str(row.id) for row in rows if row.pending] == ["10000000-0000-0000-0000-000000000020"]
        with pytest.raises(IntegrityError):
            async with migrated_engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO pending_feature_mentions (id, session_id, raw_mention, created_at) VALUES ('10000000-0000-0000-0000-000000000023', :session_id, 'VF 9', now())"
                    ),
                    {"session_id": session_id},
                )
        async with migrated_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE pending_feature_mentions SET applied_at = now() WHERE id = '10000000-0000-0000-0000-000000000020'"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO pending_feature_mentions (id, session_id, raw_mention, created_at) VALUES ('10000000-0000-0000-0000-000000000022', :session_id, 'VF 9', now())"
                ),
                {"session_id": session_id},
            )
        downgrade_again = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0006"
        )
        assert downgrade_again.returncode == 0, downgrade_again.stderr
        async with migrated_engine.connect() as connection:
            index_names = await connection.run_sync(
                lambda sync: {index["name"] for index in inspect(sync).get_indexes("pending_feature_mentions")}
            )
            count = await connection.scalar(text("SELECT count(*) FROM pending_feature_mentions"))
        assert "uq_pending_feature_mentions_session_mention" not in index_names
        assert count == 4

    @pytest.mark.asyncio
    async def test_downgrade_base_preserves_probe_then_reupgrade_restores_agent_schema(
        self, migrated_engine: AsyncEngine, agent_database_url: str
    ) -> None:
        # Given
        async with migrated_engine.begin() as connection:
            await connection.execute(text("CREATE TABLE integration_probe (id integer PRIMARY KEY)"))

        # When
        downgrade = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "base")
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            tables_after_downgrade = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            views_after_downgrade = await connection.run_sync(lambda sync: set(inspect(sync).get_view_names()))
        reupgrade = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head")
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            tables_after_reupgrade = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))

        # Then
        assert downgrade.returncode == 0, downgrade.stderr
        assert EXPECTED_AGENT_TABLES.isdisjoint(tables_after_downgrade)
        assert "funnel_metrics" not in views_after_downgrade
        assert "integration_probe" in tables_after_downgrade
        assert reupgrade.returncode == 0, reupgrade.stderr
        assert EXPECTED_AGENT_TABLES <= tables_after_reupgrade
        assert "integration_probe" in tables_after_reupgrade

    @pytest.mark.asyncio
    async def test_downgrade_drops_view_then_reupgrade_restores_schema(
        self, migrated_engine: AsyncEngine, agent_database_url: str
    ) -> None:
        # Given
        # When
        downgrade_view = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0005"
        )
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            views_after_downgrade = await connection.run_sync(lambda sync: set(inspect(sync).get_view_names()))
        reupgrade = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head")
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            views_after_reupgrade = await connection.run_sync(lambda sync: set(inspect(sync).get_view_names()))

        # Then
        assert downgrade_view.returncode == 0, downgrade_view.stderr
        assert "funnel_metrics" not in views_after_downgrade
        assert reupgrade.returncode == 0, reupgrade.stderr
        assert EXPECTED_AGENT_TABLES <= tables
        assert "funnel_metrics" in views_after_reupgrade


def _assert_live_schema_matches_metadata(connection: Connection, metadata_tables: dict[str, Table]) -> None:
    """Assert inspectable PostgreSQL DDL matches the Agent SQLAlchemy metadata."""
    inspector = inspect(connection)
    for table_name, metadata_table in metadata_tables.items():
        _assert_columns_match(inspector.get_columns(table_name), metadata_table)
        _assert_primary_key_matches(inspector.get_pk_constraint(table_name), metadata_table)
        _assert_foreign_keys_match(inspector.get_foreign_keys(table_name), metadata_table)
        _assert_checks_match(inspector.get_check_constraints(table_name), metadata_table)
        _assert_indexes_match(inspector.get_indexes(table_name), metadata_table)


def _assert_columns_match(live_columns: list[ReflectedColumn], metadata_table: Table) -> None:
    live_by_name = {column["name"]: column for column in live_columns}
    assert set(live_by_name) == {column.name for column in metadata_table.columns}
    for metadata_column in metadata_table.columns:
        live_column = live_by_name[metadata_column.name]
        assert cast(Any, live_column["type"]).compile(dialect=postgresql.dialect()) == metadata_column.type.compile(
            dialect=postgresql.dialect()
        )
        assert live_column["nullable"] is metadata_column.nullable
        assert _normalize_default(cast(str | None, live_column["default"])) == _normalize_default(
            str(cast(Any, metadata_column.server_default).arg) if metadata_column.server_default is not None else None
        )


def _assert_primary_key_matches(live_primary_key: ReflectedPrimaryKeyConstraint, metadata_table: Table) -> None:
    metadata_primary_key = next(
        constraint for constraint in metadata_table.constraints if isinstance(constraint, PrimaryKeyConstraint)
    )
    assert live_primary_key["constrained_columns"] == [column.name for column in metadata_primary_key.columns]


def _assert_foreign_keys_match(live_foreign_keys: list[ReflectedForeignKeyConstraint], metadata_table: Table) -> None:
    live_by_columns: dict[tuple[str, ...], ReflectedForeignKeyConstraint] = {
        tuple(foreign_key["constrained_columns"]): foreign_key for foreign_key in live_foreign_keys
    }
    metadata_foreign_keys = (
        constraint for constraint in metadata_table.constraints if isinstance(constraint, ForeignKeyConstraint)
    )
    for metadata_foreign_key in metadata_foreign_keys:
        columns = tuple(element.parent.name for element in metadata_foreign_key.elements)
        live_foreign_key = live_by_columns[columns]
        assert live_foreign_key["referred_table"] == metadata_foreign_key.elements[0].column.table.name
        assert live_foreign_key["referred_columns"] == [
            element.column.name for element in metadata_foreign_key.elements
        ]
        assert live_foreign_key["options"].get("ondelete") == metadata_foreign_key.ondelete


def _assert_checks_match(live_checks: list[ReflectedCheckConstraint], metadata_table: Table) -> None:
    live_by_name = {check["name"]: check["sqltext"] for check in live_checks}
    metadata_checks = (
        constraint for constraint in metadata_table.constraints if isinstance(constraint, CheckConstraint)
    )
    for metadata_check in metadata_checks:
        check_name = str(metadata_check.name)
        assert _normalize_sql(live_by_name[check_name]) == _normalize_sql(str(metadata_check.sqltext))


def _assert_indexes_match(live_indexes: list[ReflectedIndex], metadata_table: Table) -> None:
    live_by_name = {index["name"]: index for index in live_indexes}
    for metadata_index in metadata_table.indexes:
        live_index = live_by_name[metadata_index.name]
        assert live_index["unique"] is metadata_index.unique
        _assert_index_targets_match(live_index, metadata_index)
        metadata_predicate = metadata_index.dialect_options["postgresql"].get("where")
        live_predicate = live_index["dialect_options"].get("postgresql_where")
        assert _normalize_sql(live_predicate) == _normalize_sql(
            str(metadata_predicate) if metadata_predicate is not None else None
        )


def _assert_index_targets_match(live_index: ReflectedIndex, metadata_index: Index) -> None:
    """So khớp cột được đánh chỉ mục.

    Postgres phản chiếu chỉ mục trên biểu thức (vd ``profile_snapshot->>'offer_state'``)
    thành ``column_names=[None]`` và đặt biểu thức thật vào ``expressions``, nên phải so
    theo SQL đã chuẩn hoá chứ không so theo tên cột.
    """

    metadata_names = [_index_expression_name(expression) for expression in metadata_index.expressions]
    live_names = list(live_index["column_names"] or [])
    if None not in live_names:
        assert live_names == metadata_names
        return

    live_expressions = list(live_index.get("expressions") or [])
    assert len(live_expressions) == len(metadata_names)
    for live_expression, metadata_name in zip(live_expressions, metadata_names, strict=True):
        assert _normalize_index_expression(live_expression) == _normalize_index_expression(metadata_name)


def _normalize_index_expression(expression: str) -> str:
    return expression.replace(" ", "").replace("::text", "").strip("()").lower()


def _index_expression_name(expression: object) -> str:
    """Extract a column name from indexed SQLAlchemy expressions."""
    return (
        getattr(expression, "name", None)
        or getattr(getattr(expression, "element", None), "name", None)
        or str(expression).split()[0]
    )


def _normalize_default(default: str | None) -> str | None:
    return default.replace("::character varying", "").replace("'", "") if default is not None else None


def _normalize_sql(statement: str | None) -> str | None:
    if statement is None:
        return None
    normalized = " ".join(statement.split()).lower()
    normalized = re.sub(r"::[a-z ]+(?:\[\])?", "", normalized)
    normalized = normalized.replace("array[", "").replace("[", "").replace("]", "")
    normalized = normalized.replace("(", "").replace(")", "")
    normalized = normalized.replace("= any ", " in ")
    normalized = re.sub(r"\s*(<>|>=|<=)\s*", r" \1 ", normalized)
    return re.sub(r"(\w+) between (\d+) and (\d+)", r"\1 >= \2 and \1 <= \3", normalized)


def _agent_table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names()) & EXPECTED_AGENT_TABLES


# ── PR1 Foundation migration tests (T1.3, T3.7) ─────────────────────────────


class TestPr1CoreTurnLeaseMigration:
    """Test agent_0035 adds lease + result_payload columns to conversation_turn_outcomes."""

    PR1_REVISION = "agent_0035"

    @pytest.mark.asyncio
    async def test_pr1_upgrade_adds_lease_columns(self, migrated_engine: AsyncEngine, agent_database_url: str) -> None:
        # Precondition: DB session đã upgrade head → bỏ 4 cột bằng downgrade về
        # previous revision để mô phỏng trạng thái trước PR1.
        downgrade = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0034"
        )
        assert downgrade.returncode == 0, downgrade.stderr
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            cols_before = await connection.run_sync(
                lambda sync: {col["name"] for col in inspect(sync).get_columns("conversation_turn_outcomes")}
            )
        assert "claim_token" not in cols_before
        assert "claimed_at" not in cols_before
        assert "lease_expires_at" not in cols_before
        assert "result_payload" not in cols_before

        upgrade = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", self.PR1_REVISION
        )
        assert upgrade.returncode == 0, upgrade.stderr
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            cols_after = await connection.run_sync(
                lambda sync: {col["name"] for col in inspect(sync).get_columns("conversation_turn_outcomes")}
            )
        assert "claim_token" in cols_after
        assert "claimed_at" in cols_after
        assert "lease_expires_at" in cols_after
        assert "result_payload" in cols_after

    @pytest.mark.asyncio
    async def test_pr1_has_one_head(self, agent_database_url: str) -> None:
        completed = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "heads")
        assert completed.returncode == 0, completed.stderr
        heads = [line for line in completed.stdout.splitlines() if line.strip()]
        assert len(heads) == 1, completed.stdout

    @pytest.mark.asyncio
    async def test_pr1_downgrade_removes_columns(self, migrated_engine: AsyncEngine, agent_database_url: str) -> None:
        # Session DB đang ở head (đã có 4 cột). Hạ về previous revision phải bỏ
        # đúng 4 cột; nâng lại head phải phục hồi đủ.
        downgrade = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0034"
        )
        assert downgrade.returncode == 0, downgrade.stderr
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            cols_after_downgrade = await connection.run_sync(
                lambda sync: {col["name"] for col in inspect(sync).get_columns("conversation_turn_outcomes")}
            )

        reupgrade = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head")
        assert reupgrade.returncode == 0, reupgrade.stderr
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            cols_after_reupgrade = await connection.run_sync(
                lambda sync: {col["name"] for col in inspect(sync).get_columns("conversation_turn_outcomes")}
            )

        assert "claim_token" not in cols_after_downgrade
        assert "claimed_at" not in cols_after_downgrade
        assert "lease_expires_at" not in cols_after_downgrade
        assert "result_payload" not in cols_after_downgrade
        assert "claim_token" in cols_after_reupgrade
        assert "result_payload" in cols_after_reupgrade

    @pytest.mark.asyncio
    async def test_result_payload_column_properties(
        self, migrated_engine: AsyncEngine, agent_database_url: str
    ) -> None:
        upgrade = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", self.PR1_REVISION
        )
        assert upgrade.returncode == 0, upgrade.stderr
        await migrated_engine.dispose()
        async with migrated_engine.connect() as connection:
            cols = await connection.run_sync(lambda sync: inspect(sync).get_columns("conversation_turn_outcomes"))
        payload_col = next(c for c in cols if c["name"] == "result_payload")
        assert payload_col["nullable"] is True
        assert "jsonb" in str(payload_col["type"]).lower()
