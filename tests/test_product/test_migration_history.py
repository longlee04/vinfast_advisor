"""Regression checks for the Product Alembic revision graph."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_product_migration_history_has_exactly_one_head() -> None:
    """Product migrations must remain deployable with ``upgrade head``."""

    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic-products.ini", "heads"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    heads = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, completed.stdout
