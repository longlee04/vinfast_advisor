from __future__ import annotations

from types import SimpleNamespace

from migrations.agents.versions import agent_0017_output_risk_policy as migration


def test_upgrade_replaces_the_quote_tier_check(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            drop_constraint=lambda *args, **kwargs: calls.append(("drop", (args, kwargs))),
            create_check_constraint=lambda *args: calls.append(("create", args)),
        ),
    )

    migration.upgrade()

    assert migration.revision == "agent_0017"
    assert migration.down_revision == "agent_0016"
    assert calls[0][0] == "drop"
    assert "EVIDENCE_BACKED_AUTO" in str(calls[1][1])
    assert "ADVISOR_HANDOFF" in str(calls[1][1])


def test_downgrade_maps_new_tiers_before_restoring_check(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            execute=lambda statement: calls.append(("execute", statement)),
            drop_constraint=lambda *args, **kwargs: calls.append(("drop", (args, kwargs))),
            create_check_constraint=lambda *args: calls.append(("create", args)),
        ),
    )

    migration.downgrade()

    assert [name for name, _ in calls] == ["execute", "drop", "create"]
    assert "UPDATE quote_audit_log" in str(calls[0][1])
    assert "EVIDENCE_BACKED_AUTO" in str(calls[0][1])
    assert "EVIDENCE_BACKED_AUTO" not in str(calls[2][1])
