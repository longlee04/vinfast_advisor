"""Add turn_traces: one row per turn recording WHY the agent answered that way."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0030"
down_revision: str | None = "agent_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "turn_traces"


def upgrade() -> None:
    """Create the observation table.

    KHÔNG có khoá ngoại tới `conversation_sessions`: đây là bảng QUAN SÁT, nó
    phải sống sót cả khi phiên bị xoá (`delete_conversation`) — mất vệt vì khách
    xoá hội thoại là mất đúng dữ liệu cần để điều tra.
    """

    op.create_table(
        _TABLE,
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("intent_hint", sa.String(48), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("tier", sa.String(16), nullable=True),
        sa.Column("scope_label", sa.String(24), nullable=True),
        sa.Column("terminal_reason", sa.String(48), nullable=True),
        sa.Column("routing_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_turn_traces_created", _TABLE, ["created_at"])
    op.create_index("ix_turn_traces_session", _TABLE, ["session_id"])
    op.create_index("ix_turn_traces_tier", _TABLE, ["tier"])


def downgrade() -> None:
    """Drop the observation table and its indexes."""

    op.drop_index("ix_turn_traces_tier", table_name=_TABLE)
    op.drop_index("ix_turn_traces_session", table_name=_TABLE)
    op.drop_index("ix_turn_traces_created", table_name=_TABLE)
    op.drop_table(_TABLE)
