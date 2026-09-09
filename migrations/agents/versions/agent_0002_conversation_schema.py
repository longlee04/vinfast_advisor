"""Create conversation and customer-profile tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "agent_0002"
down_revision: str | None = "agent_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_sessions",
        sa.Column("session_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("customer_id", sa.String(64), nullable=False),
        sa.Column("assigned_advisor_id", sa.String(64)),
        sa.Column("vehicle_type_hint", sa.String(32)),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'COMPLETED', 'ABANDONED')", name="ck_conversation_sessions_status"),
        sa.CheckConstraint(
            "vehicle_type_hint IS NULL OR vehicle_type_hint IN ('CAR', 'ELECTRIC_MOTORBIKE')",
            name="ck_conversation_sessions_vehicle_type",
        ),
    )
    op.create_index(
        "ix_conversation_sessions_customer", "conversation_sessions", ["customer_id", sa.text("started_at DESC")]
    )
    op.create_index("ix_conversation_sessions_advisor", "conversation_sessions", ["assigned_advisor_id", "status"])
    op.create_table(
        "conversation_slots",
        sa.Column("session_id", UUID(as_uuid=False), nullable=False),
        sa.Column("slot_name", sa.String(64), nullable=False),
        sa.Column("slot_value_text", sa.Text()),
        sa.Column("slot_value_number", sa.Numeric(14, 3)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "slot_name"),
    )
    op.create_table(
        "pending_feature_mentions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=False),
        sa.Column("raw_mention", sa.Text(), nullable=False),
        sa.Column("feature_code", sa.String(100)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.session_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pending_feature_mentions_session", "pending_feature_mentions", ["session_id", "applied_at"])
    op.create_table(
        "customer_profiles",
        sa.Column("customer_id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(150)),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "out_of_scope_log",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=False),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.session_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "classification IN ('IN_SCOPE', 'MISSING_DATA', 'OUT_OF_SCOPE')", name="ck_out_of_scope_log_classification"
        ),
    )
    op.create_index(
        "ix_out_of_scope_log_classification", "out_of_scope_log", ["classification", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("ix_out_of_scope_log_classification", table_name="out_of_scope_log")
    op.drop_table("out_of_scope_log")
    op.drop_table("customer_profiles")
    op.drop_index("ix_pending_feature_mentions_session", table_name="pending_feature_mentions")
    op.drop_table("pending_feature_mentions")
    op.drop_table("conversation_slots")
    op.drop_index("ix_conversation_sessions_advisor", table_name="conversation_sessions")
    op.drop_index("ix_conversation_sessions_customer", table_name="conversation_sessions")
    op.drop_table("conversation_sessions")
