"""Use case đọc vệt quyết định — số liệu cho màn admin (Sếp 2026-08-26).

**Con số đáng nhìn nhất là ĐỘ PHỦ, không phải ngưỡng.** Đọc log thật trên prod
ngày 26/08: 26/27 lượt có `intent=None`, và điểm chỉ rơi vào ba giá trị
0.0 / 0.2 / 1.0 — không một lượt nào nằm trong dải `CONFIRM` [0.60, 0.85). Đi
chỉnh `NLU_AUTO_THRESHOLD` khi độ phủ ~4% là chỉnh nhầm chỗ; việc phải làm là mở
rộng `entity_catalog` cho Lớp 2 nhận ra được nhiều hơn.

Vì vậy `summarize_traces` đưa ba số lên trước: độ phủ, phân bố mức, và biểu đồ
cột của confidence — cột trống ở [0.6, 0.8) chính là bằng chứng ngưỡng đang vô dụng.

Phần tổng hợp là hàm THUẦN, tách khỏi truy vấn: nó là thứ dễ sai nhất và cũng là
thứ dễ test nhất.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

#: Bề rộng một cột biểu đồ. 0.2 chia [0,1] thành năm cột — đủ thô để đọc bằng
#: mắt, đủ mịn để thấy dải `CONFIRM` có rỗng hay không.
_BUCKET_WIDTH = 0.2
_BUCKET_LABELS: tuple[str, ...] = ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0")

#: Chặn trên cho khung thời gian và số dòng — một tham số URL không được phép
#: kéo cả bảng về.
MAX_WINDOW_HOURS = 24 * 30
MAX_ROWS = 200


@dataclass(frozen=True, slots=True)
class TraceSummary:
    """Số liệu một khung thời gian."""

    total: int
    with_intent: int
    coverage_pct: float
    tier_counts: dict[str, int] = field(default_factory=dict)
    histogram: dict[str, int] = field(default_factory=dict)


def summarize_traces(rows: Sequence[Mapping[str, Any]]) -> TraceSummary:
    """Gộp các dòng vệt thành số liệu màn admin."""

    total = len(rows)
    with_intent = sum(1 for row in rows if row.get("intent_hint"))
    tier_counts: dict[str, int] = {}
    for row in rows:
        tier = row.get("tier")
        if tier:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
    histogram = dict.fromkeys(_BUCKET_LABELS, 0)
    for row in rows:
        confidence = row.get("confidence")
        # `None` = lượt không qua Lớp 4 (lỗi giữa lượt, hoặc chưa nối). Đếm nó
        # thành 0.0 sẽ dựng một cột giả ở đáy và làm cả biểu đồ nói dối.
        if confidence is None:
            continue
        histogram[_bucket_label(float(confidence))] += 1
    return TraceSummary(
        total=total,
        with_intent=with_intent,
        coverage_pct=round(100.0 * with_intent / total, 2) if total else 0.0,
        tier_counts=tier_counts,
        histogram=histogram,
    )


def _bucket_label(confidence: float) -> str:
    """Cột chứa `confidence`. Đúng 1.0 rơi vào cột cuối, không tràn ra ngoài."""

    index = min(int(max(0.0, confidence) / _BUCKET_WIDTH), len(_BUCKET_LABELS) - 1)
    return _BUCKET_LABELS[index]


@dataclass(frozen=True)
class TurnTraceOperations:
    """Use case màn admin: thống kê + danh sách lượt gần đây."""

    unit_of_work: Any
    clock: Any

    async def stats(self, *, hours: int = 24) -> TraceSummary:
        """Số liệu trong `hours` giờ gần nhất."""

        since = self.clock.now() - timedelta(hours=max(1, min(hours, MAX_WINDOW_HOURS)))
        async with self.unit_of_work.transaction() as transaction:
            rows = await transaction.turn_traces.since(since)
        return summarize_traces(rows)

    async def recent(self, *, hours: int = 24, limit: int = 50, tier: str | None = None) -> list[dict[str, Any]]:
        """Các lượt gần nhất, mới trước, kèm trọn vệt giải thích."""

        since = self.clock.now() - timedelta(hours=max(1, min(hours, MAX_WINDOW_HOURS)))
        async with self.unit_of_work.transaction() as transaction:
            return await transaction.turn_traces.recent(since=since, limit=max(1, min(limit, MAX_ROWS)), tier=tier)


__all__ = ["TraceSummary", "TurnTraceOperations", "summarize_traces"]
