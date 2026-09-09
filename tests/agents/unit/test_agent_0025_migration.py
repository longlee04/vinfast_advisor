from __future__ import annotations

from types import SimpleNamespace

import sqlalchemy as sa

from migrations.agents.versions import agent_0025_turn_bottleneck_signals as migration


def test_upgrade_creates_exact_bottleneck_signal_schema(monkeypatch) -> None:
    tables: list[tuple[str, tuple[object, ...]]] = []
    indexes: list[tuple[str, str, list[str]]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            create_table=lambda name, *items: tables.append((name, items)),
            create_index=lambda name, table, columns: indexes.append((name, table, columns)),
        ),
    )

    migration.upgrade()

    assert migration.revision == "agent_0025"
    assert migration.down_revision == "agent_0024"
    assert [name for name, _ in tables] == ["conversation_turn_bottlenecks"]
    items = tables[0][1]
    ddl = " ".join(str(item) for item in items)
    for required in (
        "signal_id",
        "session_id",
        "client_turn_id",
        "anchor_client_turn_id",
        "evidence_quote",
        "model_name",
        "prompt_version",
        "claimed_by",
        "claimed_at",
        "lease_expires_at",
        "advisor_id",
        "decided_at",
    ):
        assert required in ddl
    check_expressions = {str(item.sqltext) for item in items if isinstance(item, sa.CheckConstraint)}
    assert check_expressions == {
        "label IN ('PRICE', 'CHARGING', 'BATTERY', 'RANGE')",
        "status IN ('PENDING', 'CORRECT', 'INCORRECT')",
        "(claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL) OR "
        "(claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)",
    }
    assert indexes == [
        (
            "ix_conversation_turn_bottlenecks_status_lease_created",
            "conversation_turn_bottlenecks",
            ["status", "lease_expires_at", "created_at"],
        ),
        (
            "ix_conversation_turn_bottlenecks_session_status_created",
            "conversation_turn_bottlenecks",
            ["session_id", "status", "created_at"],
        ),
        (
            "ix_conversation_turn_bottlenecks_anchor",
            "conversation_turn_bottlenecks",
            ["anchor_client_turn_id"],
        ),
    ]


def test_downgrade_drops_only_bottleneck_signal_schema(monkeypatch) -> None:
    dropped_indexes: list[tuple[str, str]] = []
    dropped_tables: list[str] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            drop_index=lambda name, table_name: dropped_indexes.append((name, table_name)),
            drop_table=dropped_tables.append,
        ),
    )

    migration.downgrade()

    assert dropped_indexes == [
        (
            "ix_conversation_turn_bottlenecks_anchor",
            "conversation_turn_bottlenecks",
        ),
        (
            "ix_conversation_turn_bottlenecks_session_status_created",
            "conversation_turn_bottlenecks",
        ),
        (
            "ix_conversation_turn_bottlenecks_status_lease_created",
            "conversation_turn_bottlenecks",
        ),
    ]
    assert dropped_tables == ["conversation_turn_bottlenecks"]
