"""Merge the vehicle-image and showcase Product migration branches.

Revision ID: f7e8d9c0b1a2
Revises: 773b826c346b, c1d2e3f4a5b6
Create Date: 2026-08-13
"""

from collections.abc import Sequence

revision: str = "f7e8d9c0b1a2"
down_revision: tuple[str, str] = ("773b826c346b", "c1d2e3f4a5b6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge both histories without changing the Product schema."""


def downgrade() -> None:
    """Split history back to both parent revisions without changing schema."""
