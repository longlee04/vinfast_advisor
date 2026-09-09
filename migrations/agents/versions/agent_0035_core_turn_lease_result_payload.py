"""PR1: lease fields + result_payload JSONB trên conversation_turn_outcomes.

Thêm ba cột lease (claim_token, claimed_at, lease_expires_at) và cột
result_payload JSONB làm nguồn replay canonical của kết quả lượt. Mọi cột
nullable để hàng cũ terminal-safe, không tạo token giả.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "agent_0035"
down_revision: str | None = "agent_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversation_turn_outcomes", sa.Column("claim_token", sa.UUID(), nullable=True))
    op.add_column("conversation_turn_outcomes", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "conversation_turn_outcomes", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("conversation_turn_outcomes", sa.Column("result_payload", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversation_turn_outcomes", "result_payload")
    op.drop_column("conversation_turn_outcomes", "lease_expires_at")
    op.drop_column("conversation_turn_outcomes", "claimed_at")
    op.drop_column("conversation_turn_outcomes", "claim_token")
