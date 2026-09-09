"""`conversation_core_state.booking_id` — lịch lái thử đã đặt trong phiên (đợt 9, câu kết theo checklist)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agent_0033"
down_revision: str | None = "agent_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_core_state"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "booking_id")
