"""Customer 360 — cơ hội mua, gắn phiên → cơ hội, phản hồi của TVV (plan Customer 360 Phase 4).

- `customer_opportunities`: một nhu cầu mua của một khách (tầng Cơ hội, plan §2.1). Giữ
  slot đã gom (`slots_snapshot`), lịch sử đổi slot (`slot_history`), giai đoạn và độ nóng
  đã tính sẵn — đường đọc không tính lại.
- `session_opportunity`: mỗi phiên gắn đúng 0/1 cơ hội. `kind=SUPPORT` ↔ không gắn.
- `customer360_feedback`: TVV Tách/Gộp phiên, báo sai insight — nguồn của tab "Chất lượng
  trích xuất" (Phase 6).
- Gieo 4 cờ TẮT trong `agent_feature_flags`.

Không FK tới `customer_profiles` (bảng đó có thể chưa có hàng cho khách) — cùng quy ước
`conversation_sessions.customer_id`. `downgrade` xoá đúng những gì bản này tạo.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0037"
down_revision: str | None = "agent_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FLAGS: tuple[str, ...] = (
    "customer360_attach",
    "customer360_extractor",
    "customer360_ui",
    "agent_ask_purchase_timeframe",
)


def upgrade() -> None:
    op.create_table(
        "customer_opportunities",
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("vehicle_type", sa.String(length=32), nullable=True),
        sa.Column("buyer_for", sa.String(length=16), nullable=False, server_default=sa.text("'SELF'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("replaced_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slots_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("slot_history", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("stage", sa.String(length=16), nullable=False, server_default=sa.text("'DISCOVER'")),
        sa.Column("heat_score", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("heat_band", sa.String(length=8), nullable=False, server_default=sa.text("'COLD'")),
        sa.Column("heat_breakdown", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("heat_version", sa.String(length=16), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["replaced_by"],
            ["customer_opportunities.opportunity_id"],
            name="fk_customer_opportunities_replaced_by",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "vehicle_type IS NULL OR vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')",
            name="ck_customer_opportunities_vehicle_type",
        ),
        sa.CheckConstraint(
            "buyer_for IN ('SELF', 'FAMILY', 'COMPANY', 'OTHER')", name="ck_customer_opportunities_buyer_for"
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'DORMANT', 'WON', 'LOST', 'REPLACED')", name="ck_customer_opportunities_status"
        ),
        sa.CheckConstraint(
            "stage IN ('DISCOVER', 'COMPARE', 'QUOTE', 'TEST_DRIVE', 'CLOSE')", name="ck_customer_opportunities_stage"
        ),
        sa.CheckConstraint("heat_score BETWEEN 0 AND 100", name="ck_customer_opportunities_heat_score"),
        sa.CheckConstraint("heat_band IN ('HOT', 'WARM', 'COLD')", name="ck_customer_opportunities_heat_band"),
        sa.CheckConstraint(
            "(status = 'REPLACED') = (replaced_by IS NOT NULL)", name="ck_customer_opportunities_replaced_pair"
        ),
    )
    op.create_index("ix_customer_opportunities_customer_status", "customer_opportunities", ["customer_id", "status"])
    op.create_index("ix_customer_opportunities_heat", "customer_opportunities", ["status", sa.text("heat_score DESC")])
    op.create_index("ix_customer_opportunities_last_seen", "customer_opportunities", ["last_seen_at"])

    op.create_table(
        "session_opportunity",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("decided_by", sa.String(length=8), nullable=False),
        sa.Column("decided_by_actor", sa.String(length=64), nullable=True),
        sa.Column("rule_code", sa.String(length=8), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evaluated_through_turn", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("extracted_through_turn", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("extraction_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["conversation_sessions.session_id"],
            name="fk_session_opportunity_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["customer_opportunities.opportunity_id"],
            name="fk_session_opportunity_opportunity",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("kind IN ('SALES', 'SUPPORT')", name="ck_session_opportunity_kind"),
        sa.CheckConstraint("decided_by IN ('RULE', 'LLM', 'ADVISOR')", name="ck_session_opportunity_decided_by"),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_session_opportunity_confidence"
        ),
        sa.CheckConstraint(
            "kind = 'SALES' OR opportunity_id IS NULL", name="ck_session_opportunity_support_unattached"
        ),
    )
    op.create_index("ix_session_opportunity_opportunity", "session_opportunity", ["opportunity_id"])
    op.create_index(
        "ix_session_opportunity_review",
        "session_opportunity",
        ["needs_review"],
        postgresql_where=sa.text("needs_review"),
    )

    op.create_table(
        "customer360_feedback",
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("insight_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("from_opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_decided_by", sa.String(length=8), nullable=True),
        sa.Column("field", sa.String(length=32), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('INSIGHT_WRONG', 'INSIGHT_OK', 'SESSION_MOVED', 'SESSION_SPLIT')",
            name="ck_customer360_feedback_kind",
        ),
    )
    op.create_index(
        "ix_customer360_feedback_kind_created", "customer360_feedback", ["kind", sa.text("created_at DESC")]
    )

    values = ", ".join(f"('{name}', FALSE)" for name in FLAGS)
    op.execute(f"INSERT INTO agent_feature_flags (name, enabled) VALUES {values} ON CONFLICT (name) DO NOTHING")


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name in FLAGS)
    op.execute(f"DELETE FROM agent_feature_flags WHERE name IN ({names})")
    op.drop_index("ix_customer360_feedback_kind_created", table_name="customer360_feedback")
    op.drop_table("customer360_feedback")
    op.drop_index("ix_session_opportunity_review", table_name="session_opportunity")
    op.drop_index("ix_session_opportunity_opportunity", table_name="session_opportunity")
    op.drop_table("session_opportunity")
    op.drop_index("ix_customer_opportunities_last_seen", table_name="customer_opportunities")
    op.drop_index("ix_customer_opportunities_heat", table_name="customer_opportunities")
    op.drop_index("ix_customer_opportunities_customer_status", table_name="customer_opportunities")
    op.drop_table("customer_opportunities")
