"""Add conversation ownership column for the AI -> PENDING_HANDOFF -> HUMAN -> AI state machine."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0029"
down_revision: str | None = "agent_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_sessions"


def upgrade() -> None:
    """Add ownership column, defaulting to AI-owned conversations."""
    op.add_column(
        _TABLE,
        sa.Column("ownership", sa.String(24), nullable=False, server_default=sa.text("'AI'")),
    )
    op.create_check_constraint(
        "ck_conversation_sessions_ownership",
        _TABLE,
        "ownership IN ('AI', 'PENDING_HANDOFF', 'HUMAN')",
    )


def downgrade() -> None:
    """Drop the ownership column and its check constraint."""
    op.drop_constraint("ck_conversation_sessions_ownership", _TABLE, type_="check")
    op.drop_column(_TABLE, "ownership")
