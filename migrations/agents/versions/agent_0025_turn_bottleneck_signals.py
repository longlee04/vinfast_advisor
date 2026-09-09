"""Create normalized customer-turn bottleneck signals and advisor tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0025"
down_revision: str | None = "agent_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_turn_bottlenecks"
_INDEXES = (
    "ix_conversation_turn_bottlenecks_status_lease_created",
    "ix_conversation_turn_bottlenecks_session_status_created",
    "ix_conversation_turn_bottlenecks_anchor",
)


def upgrade() -> None:
    """Create bottleneck signal storage with same-session outcome anchors."""
    op.create_table(
        _TABLE,
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anchor_client_turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("advisor_id", sa.String(length=64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "client_turn_id"],
            [
                "conversation_turn_outcomes.session_id",
                "conversation_turn_outcomes.client_turn_id",
            ],
            name="fk_turn_bottlenecks_current_outcome",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "anchor_client_turn_id"],
            [
                "conversation_turn_outcomes.session_id",
                "conversation_turn_outcomes.client_turn_id",
            ],
            name="fk_turn_bottlenecks_anchor_outcome",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "label IN ('PRICE', 'CHARGING', 'BATTERY', 'RANGE')",
            name="ck_conversation_turn_bottlenecks_label",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CORRECT', 'INCORRECT')",
            name="ck_conversation_turn_bottlenecks_status",
        ),
        sa.CheckConstraint(
            "(claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL) OR "
            "(claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_conversation_turn_bottlenecks_claim_triple",
        ),
        sa.UniqueConstraint(
            "session_id",
            "client_turn_id",
            name="uq_conversation_turn_bottlenecks_current_turn",
        ),
    )
    op.create_index(_INDEXES[0], _TABLE, ["status", "lease_expires_at", "created_at"])
    op.create_index(_INDEXES[1], _TABLE, ["session_id", "status", "created_at"])
    op.create_index(_INDEXES[2], _TABLE, ["anchor_client_turn_id"])


def downgrade() -> None:
    """Drop only bottleneck signal storage."""
    for index_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name=_TABLE)
    op.drop_table(_TABLE)
