"""Persist customer-visible transcript and incremental conversation summary."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0013"
down_revision: str | None = "agent_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TURN_INDEX_NAME = "ix_conversation_messages_session_turn"
_CLIENT_TURN_NAME = "uq_conversation_messages_client_turn_role"
_SESSION_ACTIVITY_NAME = "ix_conversation_sessions_customer_activity"


def upgrade() -> None:
    """Create append-only transcript and one summary row per session."""

    op.add_column(
        "conversation_sessions",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        _SESSION_ACTIVITY_NAME,
        "conversation_sessions",
        ["customer_id", "archived_at", "last_activity_at"],
    )
    op.create_table(
        "conversation_messages",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_conversation_messages_role"),
        sa.UniqueConstraint("session_id", "turn_index", name="uq_conversation_messages_session_turn"),
    )
    op.create_table(
        "conversation_summaries",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summarized_through_turn", sa.BigInteger(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        _TURN_INDEX_NAME,
        "conversation_messages",
        ["session_id", "turn_index"],
    )
    op.create_index(
        _CLIENT_TURN_NAME,
        "conversation_messages",
        ["session_id", "client_turn_id", "role"],
        unique=True,
        postgresql_where=sa.text("client_turn_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop only memory objects introduced by this revision."""

    op.drop_index(_CLIENT_TURN_NAME, table_name="conversation_messages")
    op.drop_index(_TURN_INDEX_NAME, table_name="conversation_messages")
    op.drop_table("conversation_summaries")
    op.drop_table("conversation_messages")
    op.drop_index(_SESSION_ACTIVITY_NAME, table_name="conversation_sessions")
    op.drop_column("conversation_sessions", "archived_at")
