"""Add durable structured state for cross-turn operational tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0016"
down_revision: str | None = "agent_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add active task state and normalize legacy JSON null pending values."""

    op.add_column(
        "conversation_sessions",
        sa.Column("active_task_state", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE conversation_sessions "
            "SET pending_slot_request = NULL "
            "WHERE pending_slot_request = 'null'::jsonb"
        )
    )


def downgrade() -> None:
    """Remove only the reversible task-state column."""

    op.drop_column("conversation_sessions", "active_task_state")

