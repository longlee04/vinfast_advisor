"""Thời điểm khách định mua — câu hỏi lồng sau báo giá lăn bánh (plan Customer 360, 4G).

Hai việc thuần, không I/O:

- `parse_purchase_timeframe`: đọc câu TRẢ LỜI ngay sau câu hỏi ra mã
  `customer_insight` (`WITHIN_1_MONTH`…`UNDECIDED`). Chặt hơn từ điển kiểm
  evidence của `customer_insight` (nơi đó chỉ cần "có dính chữ tháng"): ở đây
  nhận nhầm là bot đáp "em ghi nhận" cho một câu không phải câu trả lời.
- Nhãn khách đọc của từng mã + nút trả lời nhanh — cùng một bảng, để chữ bot
  nói lại và chữ trên nút không lệch nhau.

Mã khớp `customer_insight._ALLOWED_CODES[PURCHASE_TIMEFRAME]` — insight thật vẫn
do extractor ghi (cờ `customer360_extractor`); lõi chỉ hỏi và đáp lời.
"""

from __future__ import annotations

import re
from typing import Final

from src.agents.domain.customer_insight import normalize_evidence

#: Cờ `agent_feature_flags` (gieo TẮT ở agent_0037) — theo khách (rollout/allowlist).
FLAG_ASK_PURCHASE_TIMEFRAME: Final = "agent_ask_purchase_timeframe"
#: Khoá trong `CoreState.ask_counts`: GIÁ TRỊ là số lượt (`turn_count`) lúc hỏi —
#: có khoá = phiên đã hỏi (không hỏi lại), đúng lượt kế = câu khách vừa gõ là câu trả lời.
ASK_KEY: Final = "purchase_timeframe"

WITHIN_1_MONTH: Final = "WITHIN_1_MONTH"
ONE_TO_THREE_MONTHS: Final = "1_3_MONTHS"
THREE_TO_SIX_MONTHS: Final = "3_6_MONTHS"
OVER_6_MONTHS: Final = "OVER_6_MONTHS"
UNDECIDED: Final = "UNDECIDED"

#: Mã → cụm khách đọc được, dùng trong câu "em ghi nhận anh/chị dự định nhận xe …".
TIMEFRAME_LABELS: Final[dict[str, str]] = {
    WITHIN_1_MONTH: "trong tháng này",
    ONE_TO_THREE_MONTHS: "trong 1–3 tháng tới",
    THREE_TO_SIX_MONTHS: "trong 3–6 tháng tới",
    OVER_6_MONTHS: "sau 6 tháng nữa",
    UNDECIDED: "chưa định thời điểm cụ thể",
}

#: Nút trả lời nhanh dưới câu hỏi — chữ trên nút tự `parse` ra đúng mã của nó.
QUICK_REPLIES: Final[tuple[str, ...]] = ("Trong tháng này", "1–3 tháng tới", "3–6 tháng tới", "Chưa vội")

_PHRASES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        UNDECIDED,
        re.compile(
            r"\b(chua voi|chua biet|chua quyet|chua co ke hoach|chua dinh|tham khao|thong tha|tu tu da|de tinh sau)\b"
        ),
    ),
    (OVER_6_MONTHS, re.compile(r"\b(nam sau|nam toi|sang nam|qua nam)\b")),
    (THREE_TO_SIX_MONTHS, re.compile(r"\b(nua nam|cuoi nam)\b")),
    (ONE_TO_THREE_MONTHS, re.compile(r"\b(thang sau|thang toi|vai thang|quy sau|quy toi)\b")),
    (
        WITHIN_1_MONTH,
        re.compile(
            r"\b(thang nay|trong thang|cuoi thang|tuan nay|tuan sau|tuan toi|mua ngay|lay ngay|nhan ngay"
            r"|cang som cang tot|som nhat co the)\b"
        ),
    ),
)
#: "2 tháng", "1 3 tháng" (gạch nối đã thành khoảng trắng sau `normalize_evidence`), "1 den 3 thang".
_MONTHS: Final = re.compile(r"\b(\d{1,2})(?:\s+(?:den|toi)?\s*(\d{1,2}))?\s+thang\b")


def _bucket(months: int) -> str:
    if months <= 1:
        return WITHIN_1_MONTH
    if months <= 3:
        return ONE_TO_THREE_MONTHS
    if months <= 6:
        return THREE_TO_SIX_MONTHS
    return OVER_6_MONTHS


def parse_purchase_timeframe(text: str) -> str | None:
    """Mã thời điểm mua trong câu khách, hoặc `None` khi câu không nói thời điểm.

    Số tháng thắng cụm chữ ("tháng sau hoặc 2 tháng nữa" → theo số); khoảng
    "1–3 tháng" lấy CẬN TRÊN — khách nói 1–3 tháng là chưa chắc trong tháng này.
    """

    folded = normalize_evidence(text or "")
    if not folded:
        return None
    match = _MONTHS.search(folded)
    if match:
        upper = int(match.group(2) or match.group(1))
        if upper > 0:
            return _bucket(upper)
    for code, pattern in _PHRASES:
        if pattern.search(folded):
            return code
    return None
