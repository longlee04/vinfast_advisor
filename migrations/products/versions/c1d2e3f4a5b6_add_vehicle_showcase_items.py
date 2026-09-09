"""Add source-attributed vehicle showcase content.

Revision ID: c1d2e3f4a5b6
Revises: b8c9d0e1f2a3
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_showcase_items",
        sa.Column("showcase_item_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("section_key", sa.String(40), nullable=False),
        sa.Column("item_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("media_alt", sa.String(255), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("showcase_item_id"),
        sa.UniqueConstraint("vehicle_id", "item_key", name="uq_vehicle_showcase_item_key"),
        sa.CheckConstraint("display_order >= 0", name="ck_vehicle_showcase_display_order"),
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_vehicle_showcase_status"),
    )
    op.create_index(
        "ix_vehicle_showcase_section",
        "vehicle_showcase_items",
        ["vehicle_id", "section_key", "status", "display_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_showcase_section", table_name="vehicle_showcase_items")
    op.drop_table("vehicle_showcase_items")
