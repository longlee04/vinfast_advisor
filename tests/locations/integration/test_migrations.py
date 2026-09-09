"""Locations migration chain phải độc lập với module khác."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPOSITORY_ROOT / "migrations" / "locations" / "env.py"


def test_locations_chain_uses_its_own_version_table() -> None:
    source = ENV_FILE.read_text(encoding="utf-8")

    assert 'VERSION_TABLE = "locations_alembic_version"' in source
    assert "alembic_version_products" not in source
    assert "agent_alembic_version" not in source


def test_locations_chain_only_targets_its_own_metadata() -> None:
    source = ENV_FILE.read_text(encoding="utf-8")

    assert "target_metadata = LocationsBase.metadata" in source
    assert "ProductBase" not in source
    assert "AuthBase" not in source
