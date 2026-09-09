"""Add per-session customer location for the charging-station finder."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0022"
down_revision: str | None = "agent_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the session-scoped coordinate the charging-station finder reuses."""
    op.add_column(
        "conversation_sessions",
        sa.Column("user_location", sa.dialects.postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Remove the session-scoped location column."""
    op.drop_column("conversation_sessions", "user_location")
