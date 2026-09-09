from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import Column, Index, MetaData, String, Table
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateIndex

from migrations.agents.versions import agent_0007_pending_feature_mentions_unique as migration


def test_upgrade_only_deduplicates_pending_and_creates_partial_unique_index(monkeypatch) -> None:
    executed: list[str] = []
    indexes: list[tuple[str, str, list[str], bool, object]] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            execute=lambda statement: executed.append(statement),
            create_index=lambda name, table, columns, unique, **kwargs: indexes.append(
                (name, table, columns, unique, kwargs["postgresql_where"])
            ),
        ),
    )

    migration.upgrade()

    assert "duplicate.applied_at IS NULL" in executed[0]
    assert "keeper.applied_at IS NULL" in executed[0]
    name, table, columns, unique, predicate = indexes[0]
    assert (name, table, columns, unique) == (
        "uq_pending_feature_mentions_session_mention",
        "pending_feature_mentions",
        ["session_id", "raw_mention"],
        True,
    )
    metadata = MetaData()
    pending = Table(
        "pending_feature_mentions",
        metadata,
        Column("session_id", String),
        Column("raw_mention", String),
        Column("applied_at", String),
    )
    index = Index(name, pending.c.session_id, pending.c.raw_mention, unique=True, postgresql_where=predicate)
    assert "WHERE applied_at IS NULL" in str(CreateIndex(index).compile(dialect=dialect()))


def test_downgrade_drops_only_partial_unique_index(monkeypatch) -> None:
    dropped: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration, "op", SimpleNamespace(drop_index=lambda name, table_name: dropped.append((name, table_name)))
    )

    migration.downgrade()

    assert dropped == [("uq_pending_feature_mentions_session_mention", "pending_feature_mentions")]
