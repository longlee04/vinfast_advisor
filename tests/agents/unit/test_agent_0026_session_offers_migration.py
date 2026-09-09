"""[T4] `agent_0026` thêm bảng session_offers lưu ưu đãi đã duyệt theo phiên."""

from __future__ import annotations

from types import SimpleNamespace

from migrations.agents.versions import agent_0026_session_offers as migration


def test_revision_chain_is_linear() -> None:
    assert migration.revision == "agent_0026"
    assert migration.down_revision == "agent_0025"


def test_upgrade_creates_session_offers_table(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            create_table=lambda table, *columns, **kw: calls.append(table),
            create_index=lambda name, *args, **kw: calls.append(f"idx:{name}"),
        ),
    )

    migration.upgrade()

    assert "session_offers" in calls
    assert "idx:ix_session_offers_session_status" in calls
    assert "idx:ix_session_offers_expires" in calls


def test_downgrade_drops_session_offers_table(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            drop_index=lambda name, **kw: calls.append(f"drop_idx:{name}"),
            drop_table=lambda table, **kw: calls.append(f"drop:{table}"),
        ),
    )

    migration.downgrade()

    assert "drop_idx:ix_session_offers_expires" in calls
    assert "drop_idx:ix_session_offers_session_status" in calls
    assert "drop:session_offers" in calls


def test_model_and_migration_agree_on_columns() -> None:
    from src.agents.models import SessionOfferRow

    columns = SessionOfferRow.__table__.columns
    for name in (
        "offer_id",
        "session_id",
        "source_kind",
        "source_signal_id",
        "source_review_id",
        "promotion_code",
        "value_snapshot",
        "status",
        "approved_by",
        "expires_at",
        "created_at",
        "updated_at",
    ):
        assert name in columns, name
