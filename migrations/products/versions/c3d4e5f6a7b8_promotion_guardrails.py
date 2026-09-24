"""Rào chắn ưu đãi — cột quản trị + trạng thái UNVERIFIED (plan Customer 360, Phase 5A).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-24

Thêm vào `promotions`:
- `stackable`, `priority`: cộng dồn được không, thứ tự ưu tiên khi nhiều ưu đãi cùng hợp.
- `max_uses`, `used_count`: giới hạn số suất cấp ra (tăng khi SENT — G13).
- `requires_advisor_approval`, `advisor_max_discount_vnd`: vượt ngưỡng thì phải quản lý duyệt.
- `source_meta`: metadata nguồn (crawler) — tách khỏi `eligibility_rules`, vốn là LUẬT.
- trạng thái `UNVERIFIED`: dữ liệu chưa kiểm, tuyệt đối không đến tay khách.

Backfill: dòng crawler có `eligibility_rules` KHÔNG phải DSL → chép sang `source_meta`.
KHÔNG sửa `eligibility_rules`/`status` ở đây: khi cờ `offer_rules_engine` tắt, hành vi gợi ý
ưu đãi phải y hệt trước (plan §6 Phase 5 mục 4, câu hỏi mở Q1).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_STATUS = "status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')"
_NEW_STATUS = "status IN ('DRAFT', 'UNVERIFIED', 'ACTIVE', 'EXPIRED', 'CANCELLED')"


def upgrade() -> None:
    op.add_column("promotions", sa.Column("stackable", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("promotions", sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("100")))
    op.add_column("promotions", sa.Column("max_uses", sa.Integer(), nullable=True))
    op.add_column("promotions", sa.Column("used_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(
        "promotions",
        sa.Column("requires_advisor_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("promotions", sa.Column("advisor_max_discount_vnd", sa.BigInteger(), nullable=True))
    op.add_column(
        "promotions",
        sa.Column("source_meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_check_constraint("ck_promotions_max_uses", "promotions", "max_uses IS NULL OR max_uses > 0")
    op.create_check_constraint(
        "ck_promotions_used_count", "promotions", "used_count >= 0 AND (max_uses IS NULL OR used_count <= max_uses)"
    )
    op.create_check_constraint(
        "ck_promotions_advisor_max_discount",
        "promotions",
        "advisor_max_discount_vnd IS NULL OR advisor_max_discount_vnd >= 0",
    )
    op.drop_constraint("ck_promotions_status", "promotions", type_="check")
    op.create_check_constraint("ck_promotions_status", "promotions", _NEW_STATUS)
    op.execute(
        """
        UPDATE promotions SET source_meta = eligibility_rules
        WHERE created_by = 'vinfast_policy_crawler'
          AND NOT (eligibility_rules ? 'all' OR eligibility_rules ? 'any' OR eligibility_rules ? 'field')
          AND eligibility_rules <> '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("UPDATE promotions SET status = 'DRAFT' WHERE status = 'UNVERIFIED'")
    op.drop_constraint("ck_promotions_status", "promotions", type_="check")
    op.create_check_constraint("ck_promotions_status", "promotions", _OLD_STATUS)
    op.drop_constraint("ck_promotions_advisor_max_discount", "promotions", type_="check")
    op.drop_constraint("ck_promotions_used_count", "promotions", type_="check")
    op.drop_constraint("ck_promotions_max_uses", "promotions", type_="check")
    for column in (
        "source_meta",
        "advisor_max_discount_vnd",
        "requires_advisor_approval",
        "used_count",
        "max_uses",
        "priority",
        "stackable",
    ):
        op.drop_column("promotions", column)
