"""Create advisor-approved session offers (first-class evidence, T4)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0026"
down_revision: str | None = "agent_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "session_offers"
_INDEXES = (
    "ix_session_offers_session_status",
    "ix_session_offers_expires",
)


def upgrade() -> None:
    """Create session-scoped offer grants surviving across turns."""
    op.create_table(
        _TABLE,
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(length=24), nullable=False),
        sa.Column("source_signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("promotion_code", sa.String(length=64), nullable=False),
        sa.Column("value_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("approved_by", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["conversation_sessions.session_id"],
            name="fk_session_offers_session",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'EXPIRED')",
            name="ck_session_offers_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('CONTENT_REVIEW', 'BOTTLENECK_SIGNAL')",
            name="ck_session_offers_source_kind",
        ),
    )
    op.create_index(_INDEXES[0], _TABLE, ["session_id", "status"])
    op.create_index(_INDEXES[1], _TABLE, ["expires_at"])


def downgrade() -> None:
    """Drop session offer storage."""
    for index_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name=_TABLE)
    op.drop_table(_TABLE)
