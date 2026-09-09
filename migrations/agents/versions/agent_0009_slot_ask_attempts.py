"""Track how many times each slot was asked, per session."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0009"
down_revision: str | None = "agent_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "slot_ask_attempts"


def upgrade() -> None:
    """Cho phép bỏ qua một slot sau N lần hỏi mà khách vẫn không trả lời.

    Đếm phải nằm ở DB: mỗi lượt là một request riêng, giữ trong bộ nhớ thì lượt
    sau luôn thấy 0 và agent hỏi lại vô hạn.
    """

    op.create_table(
        _TABLE,
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("slot_name", sa.String(64), primary_key=True),
        sa.Column("ask_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Bỏ đếm; hành vi quay lại hỏi lại không giới hạn."""

    op.drop_table(_TABLE)
