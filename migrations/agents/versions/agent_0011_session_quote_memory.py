"""Remember the latest quote evaluation on the session that produced it."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "agent_0011"
down_revision: str | None = "agent_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_sessions"


def upgrade() -> None:
    """Cho một lượt xác nhận biết nó đang xác nhận báo giá nào (A7-5).

    Hai cột nằm trên `conversation_sessions` chứ không phải một bảng mới: đây là
    state của PHIÊN, và `conversation_sessions` đã là nguồn sự thật của phiên
    (mục 6.9). Dựng kho riêng cho hai giá trị này là thêm một nguồn sự thật thứ
    hai cho cùng một thứ.

    Không đọc lại từ `quote_audit_log`: audit ghi bất đồng bộ, nên lượt kế tiếp
    có thể tới trước khi dòng audit kịp commit — và điều khiển luồng thì không
    được phụ thuộc vào một bản ghi có thể chưa có.
    """

    op.add_column(_TABLE, sa.Column("last_quote_evaluation", JSONB(), nullable=True))
    op.add_column(
        _TABLE, sa.Column("last_quote_sent_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Bỏ bộ nhớ báo giá; lượt xác nhận quay lại bị đánh giá như một lượt mới."""

    op.drop_column(_TABLE, "last_quote_sent_at")
    op.drop_column(_TABLE, "last_quote_evaluation")
