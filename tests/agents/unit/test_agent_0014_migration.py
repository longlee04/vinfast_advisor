from __future__ import annotations

from types import SimpleNamespace

from migrations.agents.versions import agent_0014_conversation_turn_outcomes as migration


def test_upgrade_creates_idempotent_turn_outcome_table(monkeypatch) -> None:
    tables: list[tuple[str, tuple[object, ...]]] = []
    indexes: list[tuple[str, str, list[str], bool]] = []
    dropped_constraints: list[tuple[str, str, str]] = []
    created_constraints: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            create_table=lambda name, *items: tables.append((name, items)),
            create_index=lambda name, table, columns, unique=False, **kwargs: indexes.append(
                (name, table, columns, unique)
            ),
            drop_constraint=lambda name, table, type_: dropped_constraints.append((name, table, type_)),
            create_check_constraint=lambda name, table, condition: created_constraints.append((name, table, condition)),
        ),
    )

    migration.upgrade()

    assert migration.revision == "agent_0014"
    assert migration.down_revision == "agent_0013"
    assert [name for name, _ in tables] == ["conversation_turn_outcomes"]
    ddl = " ".join(str(item) for item in tables[0][1])
    for required in (
        "client_turn_id",
        "turn_number",
        "status",
        "answer",
        "pending_question",
        "terminal_reason",
        "lookup_facts",
        "error_category",
        "review_id",
        "message_id",
    ):
        assert required in ddl
    assert indexes == [
        (
            "ix_conversation_turn_outcomes_session_status",
            "conversation_turn_outcomes",
            ["session_id", "status"],
            False,
        )
    ]
    assert dropped_constraints == [("ck_review_queue_status", "review_queue", "check")]
    assert "EXPIRED" in created_constraints[0][2]


def test_downgrade_drops_outcomes_and_restores_review_status_constraint(
    monkeypatch,
) -> None:
    dropped_indexes: list[tuple[str, str]] = []
    dropped_tables: list[str] = []
    dropped_constraints: list[tuple[str, str, str]] = []
    created_constraints: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            drop_index=lambda name, table_name: dropped_indexes.append((name, table_name)),
            drop_table=lambda name: dropped_tables.append(name),
            drop_constraint=lambda name, table, type_: dropped_constraints.append((name, table, type_)),
            create_check_constraint=lambda name, table, condition: created_constraints.append((name, table, condition)),
        ),
    )

    migration.downgrade()

    assert dropped_indexes == [("ix_conversation_turn_outcomes_session_status", "conversation_turn_outcomes")]
    assert dropped_tables == ["conversation_turn_outcomes"]
    assert dropped_constraints == [("ck_review_queue_status", "review_queue", "check")]
    assert "EXPIRED" not in created_constraints[0][2]
