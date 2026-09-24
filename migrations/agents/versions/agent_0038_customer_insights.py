"""Customer 360 — thông tin khách tự nói (`customer_insights`) + view `customer_360_facts`.

`customer_insights`: một hàng = một điều khách NÓI RA, luôn kèm `evidence_quote` và
`turn_index` khi nguồn là LLM (CHECK). Giá trị mới mâu thuẫn giá trị cũ thì hàng cũ trỏ
`superseded_by` sang hàng mới — lịch sử không bị ghi đè im lặng.

`customer_360_facts`: gom insight, nút thắt, lịch lái thử về cùng một hình để endpoint
hồ sơ đọc bằng ĐÚNG MỘT câu SQL (plan §5.6). Phase 5 `CREATE OR REPLACE` thêm nhánh ưu đãi.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0038"
down_revision: str | None = "agent_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FIELDS: tuple[str, ...] = (
    "purchase_timeframe",
    "payment_method",
    "current_vehicle",
    "trade_in",
    "decision_maker",
    "competitor_brand",
    "other_concern",
    "buyer_for",
    "customer_group",
    "registration_province",
    "home_charging",
)

FACTS_VIEW_BASE = """
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


def upgrade() -> None:
    op.create_table(
        "customer_insights",
        sa.Column("insight_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=120), nullable=False),
        sa.Column("value_code", sa.String(length=32), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("turn_index", sa.BigInteger(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1")),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["customer_opportunities.opportunity_id"],
            name="fk_customer_insights_opportunity",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["conversation_sessions.session_id"],
            name="fk_customer_insights_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["customer_insights.insight_id"],
            name="fk_customer_insights_superseded_by",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "field IN (" + ", ".join(f"'{name}'" for name in FIELDS) + ")", name="ck_customer_insights_field"
        ),
        sa.CheckConstraint("source IN ('SLOT', 'LLM', 'ADVISOR')", name="ck_customer_insights_source"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_customer_insights_confidence"),
        sa.CheckConstraint(
            "source <> 'LLM' OR (length(evidence_quote) > 0 AND turn_index IS NOT NULL)",
            name="ck_customer_insights_llm_evidence",
        ),
        sa.UniqueConstraint("session_id", "turn_index", "field", "value", name="uq_customer_insights_turn_field_value"),
    )
    op.create_index(
        "ix_customer_insights_customer_current",
        "customer_insights",
        ["customer_id", "field"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    op.create_index("ix_customer_insights_opportunity", "customer_insights", ["opportunity_id"])
    op.execute("CREATE VIEW customer_360_facts AS " + FACTS_VIEW_BASE)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS customer_360_facts")
    op.drop_index("ix_customer_insights_opportunity", table_name="customer_insights")
    op.drop_index("ix_customer_insights_customer_current", table_name="customer_insights")
    op.drop_table("customer_insights")
