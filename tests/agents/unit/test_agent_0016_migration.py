from __future__ import annotations

from types import SimpleNamespace

from migrations.agents.versions import agent_0016_active_task_state as migration


def test_upgrade_adds_active_task_and_normalizes_json_null(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            add_column=lambda table, column: calls.append(("add", (table, column.name))),
            execute=lambda statement: calls.append(("execute", str(statement))),
        ),
    )

    migration.upgrade()

    assert migration.revision == "agent_0016"
    assert migration.down_revision == "agent_0015"
    assert ("add", ("conversation_sessions", "active_task_state")) in calls
    assert any("pending_slot_request = 'null'::jsonb" in str(value) for _, value in calls)


def test_downgrade_removes_active_task_column(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(drop_column=lambda table, column: calls.append((table, column))),
    )

    migration.downgrade()

    assert calls == [("conversation_sessions", "active_task_state")]
