"""Persist per-turn recommendation cards for exact idempotent replay."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0018"
down_revision: str | None = "agent_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the recommendations JSONB column to conversation_turn_outcomes."""

    op.add_column(
        "conversation_turn_outcomes",
        sa.Column(
            "recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Drop the recommendations column."""

    op.drop_column("conversation_turn_outcomes", "recommendations")
