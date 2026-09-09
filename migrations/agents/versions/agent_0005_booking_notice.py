"""Create test-drive booking and notice tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "agent_0005"
down_revision: str | None = "agent_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_drive_bookings",
        sa.Column("booking_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("customer_id", sa.String(64), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("advisor_id", sa.String(64)),
        sa.Column("run_id", UUID(as_uuid=False)),
        sa.Column("showroom", sa.String(255), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="REQUESTED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('REQUESTED', 'CONFIRMED', 'CANCELLED')", name="ck_test_drive_bookings_status"),
    )
    op.create_index(
        "ix_test_drive_bookings_showroom_time",
        "test_drive_bookings",
        ["showroom", "scheduled_at"],
        postgresql_where=sa.text("status <> 'CANCELLED'"),
    )
    op.create_index(
        "ix_test_drive_bookings_customer", "test_drive_bookings", ["customer_id", sa.text("scheduled_at DESC")]
    )
    op.create_table(
        "internal_notices",
        sa.Column("notice_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="NORMAL"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("priority IN ('NORMAL', 'URGENT')", name="ck_internal_notices_priority"),
    )
    op.create_index("ix_internal_notices_created", "internal_notices", [sa.text("created_at DESC")])
    op.create_table(
        "notice_reads",
        sa.Column("notice_id", UUID(as_uuid=False), nullable=False),
        sa.Column("advisor_id", sa.String(64), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notice_id"], ["internal_notices.notice_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notice_id", "advisor_id"),
    )


def downgrade() -> None:
    op.drop_table("notice_reads")
    op.drop_index("ix_internal_notices_created", table_name="internal_notices")
    op.drop_table("internal_notices")
    op.drop_index("ix_test_drive_bookings_customer", table_name="test_drive_bookings")
    op.drop_index("ix_test_drive_bookings_showroom_time", table_name="test_drive_bookings")
    op.drop_table("test_drive_bookings")
