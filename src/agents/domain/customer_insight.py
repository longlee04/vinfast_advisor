"""Thông tin khách TỰ NÓI ra, trích từ hội thoại (plan Customer 360 §5.4).

LLM đề xuất; module này quyết định cái gì được ghi. Ba lớp chống suy diễn, hai lớp
sau bằng code nên không phụ thuộc prompt có được tuân thủ hay không:

1. Schema chỉ có field được phép — không có hôn nhân/thu nhập/tuổi/giới tính.
2. `evidence_quote` phải là CHUỖI CON (sau chuẩn hoá) của đúng câu khách ở `turn_index`.
3. Mã giá trị phải thuộc bảng mã của field, và field có lexicon thì bằng chứng phải
   chứa ít nhất một từ khoá của mã đó ("tháng này" mới được là WITHIN_1_MONTH).

THUẦN Python.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class InsightField(StrEnum):
    PURCHASE_TIMEFRAME = "purchase_timeframe"
    PAYMENT_METHOD = "payment_method"
    CURRENT_VEHICLE = "current_vehicle"
    TRADE_IN = "trade_in"
    DECISION_MAKER = "decision_maker"
    COMPETITOR_BRAND = "competitor_brand"
    OTHER_CONCERN = "other_concern"
    BUYER_FOR = "buyer_for"
    CUSTOMER_GROUP = "customer_group"
    #: Nguồn SLOT — tầng Khách, giữ lịch sử khi khách đổi ý.
    REGISTRATION_PROVINCE = "registration_province"
    HOME_CHARGING = "home_charging"


class InsightSource(StrEnum):
    SLOT = "SLOT"
    LLM = "LLM"
    ADVISOR = "ADVISOR"


LLM_FIELDS: Final[frozenset[InsightField]] = frozenset(
    {
        InsightField.PURCHASE_TIMEFRAME,
        InsightField.PAYMENT_METHOD,
        InsightField.CURRENT_VEHICLE,
        InsightField.TRADE_IN,
        InsightField.DECISION_MAKER,
        InsightField.COMPETITOR_BRAND,
        InsightField.OTHER_CONCERN,
        InsightField.BUYER_FOR,
        InsightField.CUSTOMER_GROUP,
    }
)
#: Thuộc về con người, không thuộc riêng nhu cầu mua nào → `opportunity_id` NULL.
CUSTOMER_LEVEL_FIELDS: Final[frozenset[InsightField]] = frozenset(
    {
        InsightField.PAYMENT_METHOD,
        InsightField.CURRENT_VEHICLE,
        InsightField.TRADE_IN,
        InsightField.DECISION_MAKER,
        InsightField.CUSTOMER_GROUP,
        InsightField.REGISTRATION_PROVINCE,
        InsightField.HOME_CHARGING,
    }
)
#: Nhiều giá trị cùng đúng một lúc — không supersede, chỉ bỏ trùng.
MULTI_VALUED_FIELDS: Final[frozenset[InsightField]] = frozenset(
    {InsightField.COMPETITOR_BRAND, InsightField.OTHER_CONCERN}
)
VALUE_CODES: Final[dict[InsightField, frozenset[str]]] = {
    InsightField.PURCHASE_TIMEFRAME: frozenset(
        {"WITHIN_1_MONTH", "1_3_MONTHS", "3_6_MONTHS", "OVER_6_MONTHS", "UNDECIDED"}
    ),
    InsightField.PAYMENT_METHOD: frozenset({"CASH", "INSTALLMENT", "UNDECIDED"}),
    InsightField.TRADE_IN: frozenset({"YES", "NO"}),
    InsightField.DECISION_MAKER: frozenset({"SELF", "SPOUSE", "PARENTS", "COMPANY", "OTHER"}),
    InsightField.BUYER_FOR: frozenset({"SELF", "FAMILY", "COMPANY", "OTHER"}),
    InsightField.CUSTOMER_GROUP: frozenset({"POLICE_MILITARY", "VNPOST", "VINCLUB", "OTHER"}),
}
#: Bằng chứng phải chứa ít nhất một cụm (đã gập dấu) cho mã tương ứng.
_LEXICON: Final[dict[tuple[InsightField, str], tuple[str, ...]]] = {
    (InsightField.PURCHASE_TIMEFRAME, "WITHIN_1_MONTH"): (
        "thang nay",
        "tuan nay",
        "tuan sau",
        "ngay",
        "som",
        "cuoi thang",
        "dau thang",
    ),
    (InsightField.PURCHASE_TIMEFRAME, "1_3_MONTHS"): ("thang", "quy", "tet"),
    (InsightField.PURCHASE_TIMEFRAME, "3_6_MONTHS"): ("thang", "nua nam", "cuoi nam", "tet"),
    (InsightField.PURCHASE_TIMEFRAME, "OVER_6_MONTHS"): ("nam sau", "nam toi", "chua voi", "thong tha", "cuoi nam"),
    (InsightField.PAYMENT_METHOD, "INSTALLMENT"): ("tra gop", "vay", "gop", "ngan hang", "tra truoc", "0 dong"),
    (InsightField.PAYMENT_METHOD, "CASH"): (
        "tien mat",
        "tra thang",
        "tra het",
        "tra mot lan",
        "mua dut",
        "thanh toan het",
    ),
    (InsightField.CUSTOMER_GROUP, "POLICE_MILITARY"): ("cong an", "quan doi", "bo doi", "si quan", "quan nhan"),
    (InsightField.CUSTOMER_GROUP, "VNPOST"): ("buu dien", "vnpost", "buu chinh"),
    (InsightField.CUSTOMER_GROUP, "VINCLUB"): ("vinclub", "vin club", "the vin", "hang the"),
}
MIN_CONFIDENCE: Final[float] = 0.6
#: Trần mỗi phiên để chặn chi phí LLM (plan §5.4).
MAX_EXTRACTIONS_PER_SESSION: Final[int] = 6


class RejectReason(StrEnum):
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    UNKNOWN_TURN = "UNKNOWN_TURN"
    NO_EVIDENCE = "NO_EVIDENCE"
    BAD_VALUE_CODE = "BAD_VALUE_CODE"
    LEXICON_MISMATCH = "LEXICON_MISMATCH"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


@dataclass(frozen=True, slots=True)
class InsightCandidate:
    field: InsightField
    value: str
    value_code: str | None
    evidence_quote: str
    turn_index: int
    confidence: float


@dataclass(frozen=True, slots=True)
class CurrentInsight:
    insight_id: str
    field: InsightField
    opportunity_id: str | None
    value: str
    value_code: str | None


class SaveAction(StrEnum):
    INSERT = "INSERT"
    SUPERSEDE = "SUPERSEDE"
    SKIP_DUPLICATE = "SKIP_DUPLICATE"


@dataclass(frozen=True, slots=True)
class SavePlan:
    action: SaveAction
    superseded_id: str | None = None


def normalize_evidence(text: str) -> str:
    """Gập dấu, chữ thường, gộp khoảng trắng, bỏ dấu câu — để so chuỗi con không vỡ vì cách gõ."""

    folded = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn").lower()
    folded = re.sub(r"[^\w\s]", " ", folded)
    return " ".join(folded.split())


def validate_candidate(
    raw: Mapping[str, object],
    user_turns: Mapping[int, str],
) -> InsightCandidate | RejectReason:
    """Một mục LLM trả về → ứng viên hợp lệ, hoặc lý do loại (để đếm, không ghi)."""

    try:
        insight_field = InsightField(str(raw.get("field")))
    except ValueError:
        return RejectReason.UNKNOWN_FIELD
    if insight_field not in LLM_FIELDS:
        return RejectReason.UNKNOWN_FIELD
    try:
        turn_index = int(raw.get("turn_index"))  # type: ignore[arg-type]
        confidence = float(raw.get("confidence"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return RejectReason.UNKNOWN_TURN
    if turn_index not in user_turns:
        return RejectReason.UNKNOWN_TURN
    if confidence < MIN_CONFIDENCE:
        return RejectReason.LOW_CONFIDENCE
    quote = str(raw.get("evidence_quote") or "").strip()
    normalized_quote = normalize_evidence(quote)
    if len(normalized_quote) < 2 or normalized_quote not in normalize_evidence(user_turns[turn_index]):
        return RejectReason.NO_EVIDENCE
    code_raw = raw.get("value_code")
    value_code = str(code_raw) if code_raw else None
    codes = VALUE_CODES.get(insight_field)
    if codes is not None and value_code not in codes:
        return RejectReason.BAD_VALUE_CODE
    keywords = _LEXICON.get((insight_field, value_code or ""))
    if keywords is not None and not any(keyword in normalized_quote for keyword in keywords):
        return RejectReason.LEXICON_MISMATCH
    value = str(raw.get("value") or value_code or "").strip()[:120]
    if not value:
        return RejectReason.BAD_VALUE_CODE
    return InsightCandidate(
        field=insight_field,
        value=value,
        value_code=value_code,
        evidence_quote=quote[:300],
        turn_index=turn_index,
        confidence=confidence,
    )


def _same_value(a_value: str, a_code: str | None, b_value: str, b_code: str | None) -> bool:
    if a_code or b_code:
        return a_code == b_code
    return normalize_evidence(a_value) == normalize_evidence(b_value)


def plan_save(
    candidate_field: InsightField,
    value: str,
    value_code: str | None,
    opportunity_id: str | None,
    current: Sequence[CurrentInsight],
) -> SavePlan:
    """Mâu thuẫn với giá trị hiện hành → SUPERSEDE (giữ lịch sử); trùng → bỏ qua."""

    scoped = [item for item in current if item.field is candidate_field and item.opportunity_id == opportunity_id]
    if any(_same_value(item.value, item.value_code, value, value_code) for item in scoped):
        return SavePlan(SaveAction.SKIP_DUPLICATE)
    if candidate_field in MULTI_VALUED_FIELDS or not scoped:
        return SavePlan(SaveAction.INSERT)
    return SavePlan(SaveAction.SUPERSEDE, superseded_id=scoped[0].insight_id)


def insight_scope(candidate_field: InsightField, opportunity_id: str | None) -> str | None:
    """Field tầng Khách không gắn cơ hội; field còn lại gắn cơ hội của phiên (nếu có)."""

    return None if candidate_field in CUSTOMER_LEVEL_FIELDS else opportunity_id


__all__ = [
    "CUSTOMER_LEVEL_FIELDS",
    "LLM_FIELDS",
    "MAX_EXTRACTIONS_PER_SESSION",
    "CurrentInsight",
    "InsightCandidate",
    "InsightField",
    "InsightSource",
    "RejectReason",
    "SaveAction",
    "SavePlan",
    "insight_scope",
    "normalize_evidence",
    "plan_save",
    "validate_candidate",
]
