"""Add customer-profile snapshot and offer review columns to the review queue.

Extends ``review_queue`` with the immutable customer profile captured at
enqueue time (``profile_snapshot``), the handoff flag, and two KPI columns
(``first_viewed_at``, ``offer_suggestion_ignored``). Adds the composite index
required by the sales-opportunity scan on active sessions.

Note: the plan names the index after ``state``, but the actual
``conversation_sessions`` column is ``status``; the index is built on
``(status, last_activity_at)`` to match the real schema.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0024"
down_revision: str | None = "agent_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add snapshot, handoff, KPI columns and supporting indexes."""
    op.add_column(
        "review_queue",
        sa.Column(
            "profile_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "review_queue",
        sa.Column(
            "handoff_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "review_queue",
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "review_queue",
        sa.Column(
            "offer_suggestion_ignored",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_review_queue_offer_state",
        "review_queue",
        [sa.text("(profile_snapshot->>'offer_state')")],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_conversation_sessions_state_last_activity",
        "conversation_sessions",
        ["status", "last_activity_at"],
    )


def downgrade() -> None:
    """Drop the added columns and indexes."""
    op.drop_index(
        "ix_conversation_sessions_state_last_activity", table_name="conversation_sessions"
    )
    op.drop_index("ix_review_queue_offer_state", table_name="review_queue")
    op.drop_column("review_queue", "offer_suggestion_ignored")
    op.drop_column("review_queue", "first_viewed_at")
    op.drop_column("review_queue", "handoff_requested")
    op.drop_column("review_queue", "profile_snapshot")
