"""Persist immutable idempotent customer turn outcomes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0014"
down_revision: str | None = "agent_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_INDEX = "ix_conversation_turn_outcomes_session_status"


def upgrade() -> None:
    """Create the turn claim and exact replay table."""

    op.drop_constraint("ck_review_queue_status", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_status",
        "review_queue",
        "status IN ('PENDING', 'APPROVED', 'EDITED', 'REJECTED', 'EXPIRED')",
    )
    op.create_table(
        "conversation_turn_outcomes",
        sa.Column("outcome_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_number", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("pending_question", sa.Text(), nullable=True),
        sa.Column("terminal_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "lookup_facts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED', 'WAITING_REVIEW', "
            "'REJECTED', 'EXPIRED')",
            name="ck_conversation_turn_outcomes_status",
        ),
        sa.UniqueConstraint(
            "session_id",
            "client_turn_id",
            name="uq_conversation_turn_outcomes_client_turn",
        ),
        sa.UniqueConstraint(
            "session_id",
            "turn_number",
            name="uq_conversation_turn_outcomes_turn_number",
        ),
    )
    op.create_index(
        _STATUS_INDEX,
        "conversation_turn_outcomes",
        ["session_id", "status"],
    )


def downgrade() -> None:
    """Drop turn outcomes and restore the previous review status constraint."""

    op.drop_index(_STATUS_INDEX, table_name="conversation_turn_outcomes")
    op.drop_table("conversation_turn_outcomes")
    op.drop_constraint("ck_review_queue_status", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_status",
        "review_queue",
        "status IN ('PENDING', 'APPROVED', 'EDITED', 'REJECTED')",
    )
