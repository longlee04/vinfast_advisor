"""Create the agent-scoped fixed-window rate-limit counters (T7a)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0027"
down_revision: str | None = "agent_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "agent_rate_limit_counters"
_EXPIRY_INDEX = "ix_agent_rate_limit_expires"


def upgrade() -> None:
    """Add the abuse counter backing `/agent/turn` rate limiting."""
    op.create_table(
        _TABLE,
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(_EXPIRY_INDEX, _TABLE, ["expires_at"])


def downgrade() -> None:
    """Drop the counter table and its expiry index."""
    op.drop_index(_EXPIRY_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
