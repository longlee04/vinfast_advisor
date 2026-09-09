"""Allow the SOCIAL scope label in the classification audit log."""

from collections.abc import Sequence

from alembic import op

revision: str = "agent_0008"
down_revision: str | None = "agent_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_out_of_scope_log_classification"
_TABLE = "out_of_scope_log"
_LABELS_WITH_SOCIAL = "'IN_SCOPE', 'SOCIAL', 'MISSING_DATA', 'OUT_OF_SCOPE'"
_LABELS_WITHOUT_SOCIAL = "'IN_SCOPE', 'MISSING_DATA', 'OUT_OF_SCOPE'"


def upgrade() -> None:
    """Widen the closed label set so social turns are audited, not dropped.

    Thiếu nhãn này thì insert vi phạm CHECK, `ClassifyScopeNode` nuốt lỗi và cho
    lượt đi tiếp như IN_SCOPE — khách vẫn được phục vụ nhưng `out_of_scope_log`
    mất hẳn dòng audit, đúng thứ guardrail A6-2 sinh ra để giữ.
    """

    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        f"classification IN ({_LABELS_WITH_SOCIAL})",
    )


def downgrade() -> None:
    """Reject SOCIAL again, sau khi dồn các dòng cũ về OUT_OF_SCOPE.

    Không dọn trước thì `create_check_constraint` vỡ vì dữ liệu đang có nhãn nằm
    ngoài tập hẹp lại.
    """

    op.execute(
        f"UPDATE {_TABLE} SET classification = 'OUT_OF_SCOPE' WHERE classification = 'SOCIAL'"
    )
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        f"classification IN ({_LABELS_WITHOUT_SOCIAL})",
    )
