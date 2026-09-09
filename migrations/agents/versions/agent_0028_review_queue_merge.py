"""Add per-session PENDING cap bookkeeping to the review queue (T7b)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0028"
down_revision: str | None = "agent_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "review_queue"


def upgrade() -> None:
    """Record how many over-cap pushes merged into a queue item, and from where."""
    op.add_column(
        _TABLE,
        sa.Column("merged_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "merged_run_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Drop the merge bookkeeping columns."""
    op.drop_column(_TABLE, "merged_run_ids")
    op.drop_column(_TABLE, "merged_count")
