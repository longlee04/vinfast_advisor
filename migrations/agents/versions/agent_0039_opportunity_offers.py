"""Ưu đãi gắn CƠ HỘI + vòng đời có log (plan Customer 360, Phase 5B).

Lựa chọn: BẢNG MỚI `opportunity_offers`, KHÔNG thêm `opportunity_id` vào `session_offers`.
`session_offers.status='ACTIVE'` là giấy phép cho agent nhắc ưu đãi với khách; nhét trạng thái
SUGGESTED/APPROVED vào đó có nguy cơ agent đọc ưu đãi CHƯA gửi. Vòng đời sống ở bảng mới; chỉ
khi SENT mới ghi `session_offers` (kèm `opportunity_offer_id` để truy ngược).

`opportunity_offer_events`: mỗi lần đổi trạng thái đúng một dòng — nguồn đo hiệu quả ưu đãi.
View `customer_360_facts` thêm nhánh OFFER. Gieo 2 cờ TẮT.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0039"
down_revision: str | None = "agent_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FLAGS: tuple[str, ...] = ("offer_rules_engine", "offer_lifecycle")
STATUSES = "('SUGGESTED', 'APPROVED', 'SENT', 'ENGAGED', 'CONVERTED', 'EXPIRED', 'DISMISSED')"

_VIEW_0038 = """
SELECT 'INSIGHT'::varchar AS kind,
       ci.insight_id::text AS ref_id,
       ci.customer_id,
       ci.opportunity_id::text AS opportunity_id,
       ci.session_id::text AS session_id,
       ci.field::varchar AS code,
       ci.value,
       ci.value_code,
       ci.evidence_quote,
       ci.turn_index,
       NULL::varchar AS status,
       ci.source::varchar AS source,
       (ci.superseded_by IS NULL) AS is_current,
       ci.extracted_at AS at
FROM customer_insights ci
UNION ALL
SELECT 'BOTTLENECK', b.signal_id::text, s.customer_id, so.opportunity_id::text, b.session_id::text,
       b.label::varchar, NULL, NULL, b.evidence_quote, o.turn_number, b.status::varchar, 'BOTTLENECK', TRUE,
       b.created_at
FROM conversation_turn_bottlenecks b
JOIN conversation_sessions s ON s.session_id = b.session_id
LEFT JOIN session_opportunity so ON so.session_id = b.session_id
LEFT JOIN conversation_turn_outcomes o ON o.session_id = b.session_id AND o.client_turn_id = b.client_turn_id
WHERE b.status <> 'INCORRECT'
UNION ALL
SELECT 'BOOKING', t.booking_id::text, t.customer_id, NULL, NULL, 'test_drive', t.vehicle_id::text, NULL,
       t.showroom, NULL, t.status::varchar, 'BOOKING', TRUE, t.scheduled_at
FROM test_drive_bookings t
"""
_VIEW_0039 = (
    _VIEW_0038
    + """
UNION ALL
SELECT 'OFFER', f.offer_id::text, f.customer_id, f.opportunity_id::text, NULL, f.promotion_code,
       f.discount_vnd::text, f.eligibility::varchar, NULL, NULL, f.status::varchar, 'OFFER', TRUE, f.updated_at
FROM opportunity_offers f
"""
)


def upgrade() -> None:
    op.create_table(
        "opportunity_offers",
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("promotion_code", sa.String(length=100), nullable=False),
        sa.Column("eligibility", sa.String(length=12), nullable=False),
        sa.Column("eligibility_reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("proposed_value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("discount_vnd", sa.BigInteger(), nullable=True),
        sa.Column("needs_manager_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("suggested_by", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_offer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["customer_opportunities.opportunity_id"],
            name="fk_opportunity_offers_opportunity",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"status IN {STATUSES}", name="ck_opportunity_offers_status"),
        sa.CheckConstraint("eligibility IN ('ELIGIBLE', 'NEED_INFO')", name="ck_opportunity_offers_eligibility"),
        sa.CheckConstraint("discount_vnd IS NULL OR discount_vnd >= 0", name="ck_opportunity_offers_discount"),
        sa.CheckConstraint(
            "(status IN ('SUGGESTED', 'DISMISSED')) OR approved_by IS NOT NULL",
            name="ck_opportunity_offers_approved_before_send",
        ),
    )
    op.create_index(
        "uq_opportunity_offers_live",
        "opportunity_offers",
        ["opportunity_id", "promotion_code"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('EXPIRED', 'DISMISSED')"),
    )
    op.create_index("ix_opportunity_offers_customer", "opportunity_offers", ["customer_id", "status"])
    op.create_table(
        "opportunity_offer_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_code", sa.String(length=100), nullable=False),
        sa.Column("from_status", sa.String(length=12), nullable=True),
        sa.Column("to_status", sa.String(length=12), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["offer_id"], ["opportunity_offers.offer_id"], name="fk_opportunity_offer_events_offer", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_opportunity_offer_events_status", "opportunity_offer_events", ["to_status", "created_at"])
    op.create_index(
        "ix_opportunity_offer_events_promotion", "opportunity_offer_events", ["promotion_code", "to_status"]
    )
    op.add_column("session_offers", sa.Column("opportunity_offer_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.drop_constraint("ck_session_offers_source_kind", "session_offers", type_="check")
    op.create_check_constraint(
        "ck_session_offers_source_kind",
        "session_offers",
        "source_kind IN ('CONTENT_REVIEW', 'BOTTLENECK_SIGNAL', 'OPPORTUNITY_OFFER')",
    )
    op.execute("DROP VIEW IF EXISTS customer_360_facts")
    op.execute("CREATE VIEW customer_360_facts AS " + _VIEW_0039)
    values = ", ".join(f"('{name}', FALSE)" for name in FLAGS)
    op.execute(f"INSERT INTO agent_feature_flags (name, enabled) VALUES {values} ON CONFLICT (name) DO NOTHING")


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name in FLAGS)
    op.execute(f"DELETE FROM agent_feature_flags WHERE name IN ({names})")
    op.execute("DROP VIEW IF EXISTS customer_360_facts")
    op.execute("CREATE VIEW customer_360_facts AS " + _VIEW_0038)
    op.execute("DELETE FROM session_offers WHERE source_kind = 'OPPORTUNITY_OFFER'")
    op.drop_constraint("ck_session_offers_source_kind", "session_offers", type_="check")
    op.create_check_constraint(
        "ck_session_offers_source_kind", "session_offers", "source_kind IN ('CONTENT_REVIEW', 'BOTTLENECK_SIGNAL')"
    )
    op.drop_column("session_offers", "opportunity_offer_id")
    op.drop_index("ix_opportunity_offer_events_promotion", table_name="opportunity_offer_events")
    op.drop_index("ix_opportunity_offer_events_status", table_name="opportunity_offer_events")
    op.drop_table("opportunity_offer_events")
    op.drop_index("ix_opportunity_offers_customer", table_name="opportunity_offers")
    op.drop_index("uq_opportunity_offers_live", table_name="opportunity_offers")
    op.drop_table("opportunity_offers")
