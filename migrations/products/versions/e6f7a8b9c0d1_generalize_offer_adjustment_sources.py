"""Generalize offer-adjustment audit identity across review and signal sources.

Revision ID: e6f7a8b9c0d1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add typed source identity, backfill reviews, then enforce source contract."""
    op.add_column(
        "offer_adjustment_log",
        sa.Column("source_kind", sa.String(32), nullable=True),
    )
    op.add_column(
        "offer_adjustment_log",
        sa.Column("source_id", UUID(as_uuid=False), nullable=True),
    )
    op.execute("UPDATE offer_adjustment_log SET source_kind = 'CONTENT_REVIEW', source_id = review_id")
    op.alter_column("offer_adjustment_log", "source_kind", nullable=False)
    op.alter_column("offer_adjustment_log", "source_id", nullable=False)
    op.alter_column("offer_adjustment_log", "review_id", nullable=True)
    op.create_check_constraint(
        "ck_offer_adjustment_log_source",
        "offer_adjustment_log",
        "(source_kind = 'CONTENT_REVIEW' AND review_id IS NOT NULL AND source_id = review_id) "
        "OR (source_kind = 'BOTTLENECK_SIGNAL' AND review_id IS NULL)",
    )
    op.create_unique_constraint(
        "uq_offer_adjustment_log_source",
        "offer_adjustment_log",
        ["source_kind", "source_id"],
    )


def downgrade() -> None:
    """Remove signal audits before restoring legacy review-only contract."""
    op.execute("DELETE FROM offer_adjustment_log WHERE source_kind = 'BOTTLENECK_SIGNAL'")
    op.drop_constraint("uq_offer_adjustment_log_source", "offer_adjustment_log", type_="unique")
    op.drop_constraint("ck_offer_adjustment_log_source", "offer_adjustment_log", type_="check")
    op.alter_column("offer_adjustment_log", "review_id", nullable=False)
    op.drop_column("offer_adjustment_log", "source_id")
    op.drop_column("offer_adjustment_log", "source_kind")
