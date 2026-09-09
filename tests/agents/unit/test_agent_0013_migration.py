from __future__ import annotations

from types import SimpleNamespace

from migrations.agents.versions import agent_0013_conversation_memory as migration


def test_upgrade_creates_message_and_summary_tables_with_expected_constraints(monkeypatch) -> None:
    tables: list[tuple[str, tuple[object, ...]]] = []
    indexes: list[tuple[str, str, list[str], bool, dict[str, object]]] = []
    columns: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            create_table=lambda name, *items: tables.append((name, items)),
            create_index=lambda name, table, columns, unique=False, **kwargs: indexes.append(
                (name, table, columns, unique, kwargs)
            ),
            add_column=lambda table, column: columns.append((table, column)),
        ),
    )

    migration.upgrade()

    assert migration.revision == "agent_0013"
    assert migration.down_revision == "agent_0012"
    assert [name for name, _ in tables] == [
        "conversation_messages",
        "conversation_summaries",
    ]
    assert columns[0][0] == "conversation_sessions"
    assert "archived_at" in str(columns[0][1])
    message_ddl = " ".join(str(item) for item in tables[0][1])
    assert "role" in message_ddl
    assert "turn_index" in message_ddl
    assert "client_turn_id" in message_ddl
    assert "review_id" in message_ddl
    summary_ddl = " ".join(str(item) for item in tables[1][1])
    assert "prompt_version" in summary_ddl
    assert "model_name" in summary_ddl
    assert indexes[0][:4] == (
        "ix_conversation_sessions_customer_activity",
        "conversation_sessions",
        ["customer_id", "archived_at", "last_activity_at"],
        False,
    )
    assert indexes[1][:4] == (
        "ix_conversation_messages_session_turn",
        "conversation_messages",
        ["session_id", "turn_index"],
        False,
    )
    assert indexes[2][:4] == (
        "uq_conversation_messages_client_turn_role",
        "conversation_messages",
        ["session_id", "client_turn_id", "role"],
        True,
    )
    assert "postgresql_where" in indexes[2][4]


def test_downgrade_drops_only_memory_tables_and_indexes(monkeypatch) -> None:
    dropped_indexes: list[tuple[str, str]] = []
    dropped_tables: list[str] = []
    dropped_columns: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            drop_index=lambda name, table_name: dropped_indexes.append((name, table_name)),
            drop_table=lambda name: dropped_tables.append(name),
            drop_column=lambda table, column: dropped_columns.append((table, column)),
        ),
    )

    migration.downgrade()

    assert dropped_indexes == [
        ("uq_conversation_messages_client_turn_role", "conversation_messages"),
        ("ix_conversation_messages_session_turn", "conversation_messages"),
        ("ix_conversation_sessions_customer_activity", "conversation_sessions"),
    ]
    assert dropped_tables == ["conversation_summaries", "conversation_messages"]
    assert dropped_columns == [("conversation_sessions", "archived_at")]
