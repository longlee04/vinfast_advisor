"""Widen run_candidates rank constraint from 1–3 to 1–MAX_RECOMMENDATIONS (20).

Constraint cũ `rank BETWEEN 1 AND 3` sinh ra từ thời recommendation service
luôn trả tối đa 3 xe. Sau khi `rank_candidates` bỏ giới hạn cứng và dùng
`MAX_RECOMMENDATIONS = 20` làm trần an toàn, mọi lượt trả về 4+ xe đều vỡ
constraint này và bị handler `SQLAlchemyError` toàn cục chuyển thành 503.

Chiều downgrade: khôi phục `1 AND 3`, chấp nhận rằng data có rank > 3 sẽ
không đi qua downgrade được nếu đã có hàng vi phạm — đây là thay đổi thuận
chiều và không có sản phẩm nào dựa vào trần cũ.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "agent_0020"
down_revision: str | None = "agent_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONSTRAINT = "rank IS NULL OR rank BETWEEN 1 AND 3"
_NEW_CONSTRAINT = "rank IS NULL OR rank BETWEEN 1 AND 20"
_CONSTRAINT_NAME = "ck_run_candidates_rank"
_TABLE = "run_candidates"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, _TABLE, _NEW_CONSTRAINT)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, _TABLE, _OLD_CONSTRAINT)
