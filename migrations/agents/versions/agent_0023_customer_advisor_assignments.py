"""Add customer_advisor_assignments and conversation_reassignments tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "agent_0023"
down_revision: str | None = "agent_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create customer_advisor_assignments and conversation_reassignments tables."""
    op.create_table(
        "customer_advisor_assignments",
        sa.Column("assignment_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", sa.String(64), nullable=False),
        sa.Column("advisor_id", sa.String(64), nullable=False),
        sa.Column("assigned_by", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_customer_advisor_assignments_customer",
        "customer_advisor_assignments",
        ["customer_id", "status"],
    )
    op.create_index(
        "ix_customer_advisor_assignments_advisor",
        "customer_advisor_assignments",
        ["advisor_id", "status"],
    )

    op.create_table(
        "conversation_reassignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_advisor_id", sa.String(64), nullable=True),
        sa.Column("new_advisor_id", sa.String(64), nullable=False),
        sa.Column("reassigned_by", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversation_reassignments_session",
        "conversation_reassignments",
        ["session_id"],
    )


def downgrade() -> None:
    """Drop customer_advisor_assignments and conversation_reassignments tables."""
    op.drop_index("ix_conversation_reassignments_session", table_name="conversation_reassignments")
    op.drop_table("conversation_reassignments")
    op.drop_index("ix_customer_advisor_assignments_advisor", table_name="customer_advisor_assignments")
    op.drop_index("ix_customer_advisor_assignments_customer", table_name="customer_advisor_assignments")
    op.drop_table("customer_advisor_assignments")
