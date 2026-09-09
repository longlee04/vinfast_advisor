"""Create human review queue."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "agent_0004"
down_revision: str | None = "agent_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_queue",
        sa.Column("review_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("claimed_by", sa.String(64)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("advisor_id", sa.String(64)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("edited_content", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'EDITED', 'REJECTED')", name="ck_review_queue_status"),
        sa.CheckConstraint(
            "(claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL) OR (claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_review_queue_claim_pair",
        ),
    )
    op.create_index("ix_review_queue_status_lease", "review_queue", ["status", "lease_expires_at"])
    op.create_index("ix_review_queue_session", "review_queue", ["session_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_review_queue_session", table_name="review_queue")
    op.drop_index("ix_review_queue_status_lease", table_name="review_queue")
    op.drop_table("review_queue")
