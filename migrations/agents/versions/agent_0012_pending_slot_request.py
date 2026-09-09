"""Remember which slot the assistant is waiting on, across turns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "agent_0012"
down_revision: str | None = "agent_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_sessions"


def upgrade() -> None:
    """Cho câu trả lời một-hai chữ nối được vào câu hỏi bot vừa đặt (A7-10).

    Bot hỏi tỉnh, khách đáp "hà nội", và câu đó bị gắn OUT_OF_SCOPE vì đứng riêng
    thì không khớp intent nào. Thiếu chính là chỗ ghi "đang chờ slot nào, cho
    intent nào" — cột này là chỗ đó.

    Một cột JSONB thay vì bốn cột rời: đây là MỘT bản ghi nguyên khối, đọc và ghi
    luôn cùng lúc, không có truy vấn nào lọc theo từng trường bên trong.
    """

    op.add_column(_TABLE, sa.Column("pending_slot_request", JSONB(), nullable=True))


def downgrade() -> None:
    """Bỏ bộ nhớ pending; câu trả lời ngắn quay lại bị đọc như tin nhắn rời."""

    op.drop_column(_TABLE, "pending_slot_request")
