"""Add offer adjustment policies, adjustment log and promotion gift groups.

Creates the ADMIN-configured per-type adjustment boundaries
(``offer_adjustment_policies``), the audit log for every advisor adjustment
(``offer_adjustment_log``), and the ``gift_group`` column on ``promotions`` so
GIFT offers can be matched to the right customer concern.

Note: ``offer_adjustment_log.review_id`` is a plain UUID column, NOT a foreign
key — ``review_queue`` lives in the agents module whose migrations run after
products; a cross-module FK would break ``alembic -c alembic-products.ini``.
Reference integrity is enforced at the application boundary instead.

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROMOTION_TYPES = (
    "'FIXED_DISCOUNT', 'PERCENT_DISCOUNT', 'GIFT', "
    "'FINANCING', 'REGISTRATION_SUPPORT', 'OTHER'"
)


def upgrade() -> None:
    """Create the policy and log tables, then seed defaults and gift groups."""
    op.create_table(
        "offer_adjustment_policies",
        sa.Column("promotion_type", sa.String(40), primary_key=True),
        sa.Column("adjust_min_vnd", sa.BigInteger(), nullable=True),
        sa.Column("adjust_max_vnd", sa.BigInteger(), nullable=True),
        sa.Column("adjust_min_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("adjust_max_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("financing_months_min", sa.Integer(), nullable=True),
        sa.Column("financing_months_max", sa.Integer(), nullable=True),
        sa.Column("financing_support_max_vnd", sa.BigInteger(), nullable=True),
        sa.Column("gift_value_max_vnd", sa.BigInteger(), nullable=True),
        sa.Column("allowed_gift_codes", JSONB(), nullable=True),
        sa.Column("registration_support_max_vnd", sa.BigInteger(), nullable=True),
        sa.Column("other_max_vnd", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.CheckConstraint(
            f"promotion_type IN ({_PROMOTION_TYPES})",
            name="ck_offer_adjustment_policies_type",
        ),
    )
    op.create_table(
        "offer_adjustment_log",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("review_id", UUID(as_uuid=False), nullable=False),
        sa.Column("advisor_id", sa.String(64), nullable=False),
        sa.Column("promotion_code", sa.String(100), nullable=False),
        sa.Column("adjustment_type", sa.String(40), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("promotions", sa.Column("gift_group", sa.String(50), nullable=True))

    # Seed gift_group cho promotions GIFT hiện có: 3 nhóm tối thiểu — CHARGING
    # (bộ sạc, tháng sạc, lắp đặt trạm), WARRANTY (bảo hành pin, bảo hành mở
    # rộng), OTHER (quà chung). Heuristic theo title; chưa phân loại được thì
    # mặc định OTHER để offer_matching vẫn có nhóm mà không chặn khớp.
    op.execute(
        """
        UPDATE promotions
        SET gift_group = CASE
            WHEN title ILIKE '%sạc%' OR title ILIKE '%trạm%' OR title ILIKE '%lắp đặt%'
                THEN 'CHARGING'
            WHEN title ILIKE '%bảo hành%' OR title ILIKE '%pin%'
                THEN 'WARRANTY'
            ELSE 'OTHER'
        END
        WHERE promotion_type = 'GIFT'
        """
    )

    # Seed mặc định 6 row per promotion_type. [GIẢ ĐỊNH] bound là phỏng đoán
    # khởi đầu, ADMIN tinh chỉnh sau qua API.
    op.execute(
        """
        INSERT INTO offer_adjustment_policies (
            promotion_type, adjust_min_vnd, adjust_max_vnd, adjust_min_percent,
            adjust_max_percent, financing_months_min, financing_months_max,
            financing_support_max_vnd, gift_value_max_vnd, allowed_gift_codes,
            registration_support_max_vnd, other_max_vnd, created_at, updated_at
        ) VALUES
        ('FIXED_DISCOUNT', 0, 10000000, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
        ('PERCENT_DISCOUNT', NULL, NULL, 0, 5, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
        ('GIFT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 3000000, '[]'::jsonb, NULL, NULL, NOW(), NOW()),
        ('FINANCING', NULL, NULL, NULL, NULL, 6, 36, 20000000, NULL, NULL, NULL, NULL, NOW(), NOW()),
        ('REGISTRATION_SUPPORT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 5000000, NULL, NOW(), NOW()),
        ('OTHER', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 5000000, NOW(), NOW())
        """
    )


def downgrade() -> None:
    """Drop the seeded rows, the gift_group column and both tables."""
    op.drop_column("promotions", "gift_group")
    op.drop_table("offer_adjustment_log")
    op.drop_table("offer_adjustment_policies")
