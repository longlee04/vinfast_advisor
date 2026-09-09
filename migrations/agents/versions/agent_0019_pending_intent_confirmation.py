"""Add the pending intent-confirmation record for four-layer intent recognition."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0019"
down_revision: str | None = "agent_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store one pending confirmation per session as a single JSONB record.

    A dedicated column rather than a reuse of ``pending_slot_request``: the two
    records answer different questions ("which value is missing" versus "did we
    read the intent correctly"), carry different lifecycles, and are consumed by
    different services.  Sharing one column would force the slot resolver to
    branch on payload shape before it can do anything.

    One column instead of a table for the same reason ``pending_slot_request``
    is one column: the record is always read and written whole, and no query
    filters on a field inside it.
    """

    op.add_column(
        "conversation_sessions",
        sa.Column(
            "pending_intent_confirmation",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop the column; no other object depends on it."""

    op.drop_column("conversation_sessions", "pending_intent_confirmation")
