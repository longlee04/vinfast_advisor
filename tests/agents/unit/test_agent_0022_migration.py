"""[FIND_CHARGING_STATION] `agent_0022` thêm cột vị trí theo phiên."""

from __future__ import annotations

from types import SimpleNamespace

from migrations.agents.versions import agent_0022_session_user_location as migration


def test_upgrade_adds_the_session_user_location_column(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(add_column=lambda table, column: calls.append((table, column.name))),
    )

    migration.upgrade()

    assert migration.revision == "agent_0022"
    assert migration.down_revision == "agent_0021"
    assert calls == [("conversation_sessions", "user_location")]


def test_downgrade_removes_only_that_column(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(drop_column=lambda table, column: calls.append((table, column))),
    )

    migration.downgrade()

    assert calls == [("conversation_sessions", "user_location")]


def test_model_and_migration_agree_on_the_column_name() -> None:
    from src.agents.models import ConversationSessionRow

    assert "user_location" in ConversationSessionRow.__table__.columns
