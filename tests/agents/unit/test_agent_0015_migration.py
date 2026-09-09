from __future__ import annotations

from types import SimpleNamespace

from migrations.agents.versions import agent_0015_build_agent_compatibility as migration


def test_upgrade_repairs_objects_skipped_by_the_legacy_revision_collision(
    monkeypatch,
) -> None:
    statements: list[str] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(execute=lambda statement: statements.append(str(statement))),
    )

    migration.upgrade()

    ddl = "\n".join(statements)
    assert migration.revision == "agent_0015"
    assert migration.down_revision == "agent_0014"
    assert "CREATE TABLE IF NOT EXISTS slot_ask_attempts" in ddl
    assert "CREATE TABLE IF NOT EXISTS quote_audit_log" in ddl
    assert "ADD COLUMN IF NOT EXISTS last_quote_evaluation" in ddl
    assert "ADD COLUMN IF NOT EXISTS last_quote_sent_at" in ddl
    assert "ADD COLUMN IF NOT EXISTS pending_slot_request" in ddl
    assert "CREATE INDEX IF NOT EXISTS ix_quote_audit_log_tier" in ddl


def test_downgrade_preserves_objects_that_may_predate_the_bridge(monkeypatch) -> None:
    statements: list[str] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(execute=lambda statement: statements.append(str(statement))),
    )

    migration.downgrade()

    assert statements == []
