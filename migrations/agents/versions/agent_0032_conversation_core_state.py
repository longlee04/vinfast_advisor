"""Bảng trạng thái lõi hội thoại v2 — một hàng/phiên (spec 2026-08-29 mục 4)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0032"
down_revision: str | None = "agent_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_core_state"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("intent", sa.String(24), nullable=False),
        sa.Column("slots", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("pending", postgresql.JSONB(), nullable=True),
        sa.Column("chosen_vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommended_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("ask_counts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "stage IN ('GREETING','COLLECTING','RECOMMENDED','CHOSEN','COSTING','SCHEDULING','OFFER_REVIEW','HANDED_OFF')",
            name="ck_conversation_core_state_stage",
        ),
    )
    op.create_index("ix_conversation_core_state_updated", _TABLE, ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_conversation_core_state_updated", table_name=_TABLE)
    op.drop_table(_TABLE)
