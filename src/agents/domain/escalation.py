"""Chốt tất định đẩy lượt sang NGƯỜI, đặt trước mọi bước dùng LLM.

Ba ca dưới đây KHÔNG được để mô hình quyết định:

- khách nói thẳng là muốn gặp người,
- khách đang báo một sự cố nguy hiểm trên chính chiếc xe của họ,
- câu hỏi cần dữ liệu thẩm quyền (chính sách, TCO) mà hệ thống không có.

Toàn bộ so khớp chạy trên `CanonicalText` sinh MỘT lần tại chain (ENG REVIEW
AMENDMENT 2) — gate KHÔNG tự normalize riêng. Danh sách chuỗi cố ý HẸP: trượt
một câu diễn đạt lạ chỉ khiến lượt chảy về luồng thường — nơi vẫn còn moderation,
cổng phạm vi và guardrail đỡ — còn nới rộng thành bắt nhầm thì mỗi câu hỏi vu vơ
về an toàn lại đánh thức tư vấn viên. Độ phủ được bù bằng nhãn LLM, xem
`escalation_signals`.

Phân loại hazard theo ĐỘ MƠ HỒ (ENG REVIEW AMENDMENT 1), không theo dạng khớp:

- Hazard KHÔNG mơ hồ (`bốc cháy`, `phát nổ`, `mất phanh`, ...) giữ CRITICAL cả
  khi chỉ khớp folded (không dấu) — không dấu là chế độ gõ phổ biến, hạ mức theo
  dạng khớp sẽ tắt handoff khẩn cấp cho đa số input.
- Hazard MƠ HỒ (`đang cháy`, `bị cháy`, `ra khói` — sóng đôi với nghĩa lành
  "chạy"/"khơi") chỉ được tin khi khớp ở dạng ORIGINAL (dấu phân biệt nghĩa)
  hoặc khi có corroboration (LLM CRITICAL / human_requested). Chỉ khớp folded
  mà không corroboration thì KHÔNG handoff — và KHÔNG hạ về ELEVATED-thôi.
"""

from __future__ import annotations

from typing import Final, TypedDict

from src.agents.domain.canonical_text import (
    CanonicalText,
    MatchTier,
    build_canonical_text,
    compile_keyword_variants,
    match_tier,
)
from src.agents.domain.values import Severity

#: Khách nói thẳng muốn gặp người. KHÔNG gồm "gặp lại", "gặp xe" — phải có danh
#: từ chỉ người đứng sau.
_HUMAN_REQUESTS: Final[tuple[str, ...]] = (
    "gap tu van vien",
    "gap nhan vien",
    "gap nguoi that",
    "gap nguoi thuc",
    "noi chuyen voi tu van vien",
    "noi chuyen voi nhan vien",
    "noi chuyen voi nguoi that",
    "chuyen cho tu van vien",
    "chuyen cho nhan vien",
    "chuyen may cho nguoi",
    "cho gap nguoi",
    "cho toi gap nguoi",
    "can gap nguoi",
    "muon gap nguoi",
    # J4 (plan chống-crack): xin gặp người GIÁN TIẾP — "người có thẩm quyền",
    # "người quản lý", "cấp trên". Chỉ nhận cụm có ĐỘNG TỪ XIN GẶP ("gặp",
    # "nói chuyện") để không bắt nhầm câu nói về người quản lý/ban quản lý
    # ("ban quản lý không cho sạc dưới hầm").
    "gap nguoi co tham quyen",
    "noi chuyen voi nguoi co tham quyen",
    "gap nguoi quan ly",
    "noi chuyen voi nguoi quan ly",
    "gap cap tren",
)

#: Khách đang nói về XE CỦA CHÍNH HỌ. Thiếu vế này thì "xe điện có bốc cháy
#: không" — một câu hỏi kiến thức — cũng bị coi là sự cố.
_OWN_VEHICLE: Final[tuple[str, ...]] = (
    "xe cua toi",
    "xe toi",
    "xe cua minh",
    "xe minh",
    "xe cua em",
    "xe em",
    "xe nha toi",
    "xe dang",
    "xe bi",
    "xe vua",
)

#: Nguy hiểm ĐANG diễn ra, cần người xử lý ngay.
#:
#: `normalize` bỏ dấu nên nhiều cặp từ khác nghĩa trở thành CÙNG một chuỗi:
#: "chạy" → `chay` trùng "cháy"; "nóng" → `nong`. Vì vậy KHÔNG được để từ đơn mơ
#: hồ đứng một mình ở đây, và KHÔNG được khớp bằng `in` — "xe của tôi chạy tốt"
#: sẽ thành một báo động cứu hộ.
#:
#: Hai quy tắc cho danh sách này:
#: 1. Từ đơn chỉ được vào nếu nó không trùng dạng bỏ dấu với từ thường gặp nào
#:    ("khét", "tai nạn" an toàn; "cháy", "nổ" thì không).
#: 2. Từ mơ hồ phải đi kèm ngữ cảnh làm rõ ("bốc cháy", "pin nóng").
#:
#: Danh sách viết CÓ DẤU: `compile_keyword_variants` sinh cả dạng giữ dấu (khớp
#: `original`) lẫn dạng bỏ dấu (khớp `folded`/`leet`), nên khách gõ kiểu nào
#: cũng bắt được — và dấu là thông tin phân biệt nghĩa cho hazard mơ hồ.
_CRITICAL_HAZARDS: Final[tuple[str, ...]] = (
    "bốc cháy",
    "cháy nổ",
    "phát nổ",
    "bốc khói",
    "có khói",
    "ra khói",
    "khét",
    "mất phanh",
    "mất lái",
    "không phanh được",
    "pin nóng",
    "nóng bất thường",
    "quá nóng",
    "tai nạn",
    "đâm vào",
    "đang cháy",
    "bị cháy",
)

#: Hazard sóng đôi với nghĩa lành: "đang cháy"/"đang chạy", "bị cháy"/"bị chạy",
#: "ra khói"/"ra khơi". Chỉ tin khi khớp ORIGINAL (có dấu) hoặc có corroboration.
_AMBIGUOUS_HAZARDS: Final[frozenset[str]] = frozenset({"đang cháy", "bị cháy", "ra khói"})

#: Lo ngại/phàn nàn KHÔNG khẩn cấp — nâng mức nhưng không cưỡng bức đẩy người.
_ELEVATED_CONCERNS: Final[tuple[str, ...]] = (
    "hong",
    "loi",
    "tut pin",
    "sut pin",
    "chai pin",
    "bao hanh",
    "khong nhu quang cao",
    "that vong",
    "buc minh",
    "khieu nai",
    "doi tra",
    "hoan tien",
)

#: Variants compile MỘT lần ở module-load (ENG REVIEW AMENDMENT 3) — không mỗi lượt.
_HUMAN_REQUEST_NEEDLES: Final[tuple[str, ...]] = compile_keyword_variants(_HUMAN_REQUESTS)
_OWN_VEHICLE_NEEDLES: Final[tuple[str, ...]] = compile_keyword_variants(_OWN_VEHICLE)
_ELEVATED_CONCERN_NEEDLES: Final[tuple[str, ...]] = compile_keyword_variants(_ELEVATED_CONCERNS)
_HAZARD_NEEDLES: Final[dict[str, tuple[str, ...]]] = {
    hazard: compile_keyword_variants((hazard,)) for hazard in _CRITICAL_HAZARDS
}

_TIER_RANK: Final[dict[MatchTier, int]] = {
    MatchTier.NONE: 0,
    MatchTier.LEET: 1,
    MatchTier.FOLDED: 2,
    MatchTier.ORIGINAL: 3,
}


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Wrapper ngược-tương thích: khớp `needle` trên chuỗi đã chuẩn hoá.

    Giữ chữ ký cũ (haystack là chuỗi folded, needle là keyword folded) nhưng
    triển khai qua `match_tier` — mọi so khớp keyword đi đúng một bộ duy nhất.
    """

    canonical = CanonicalText(original=haystack, folded=haystack, leet_decoded=haystack)
    return match_tier(canonical, needle) is not MatchTier.NONE


def _any_needle_matches(canonical: CanonicalText, needles: tuple[str, ...]) -> bool:
    return any(match_tier(canonical, needle) is not MatchTier.NONE for needle in needles)


def _best_hazard_tier(canonical: CanonicalText, hazard: str) -> MatchTier:
    """Tier cao nhất trong các needle variant của một hazard."""

    best = MatchTier.NONE
    for needle in _HAZARD_NEEDLES[hazard]:
        tier = match_tier(canonical, needle)
        if _TIER_RANK[tier] > _TIER_RANK[best]:
            best = tier
    return best


def _hazard_confirmed(canonical: CanonicalText, hazard: str) -> bool:
    """Hazard có được xác nhận trên canonical không, xét độ mơ hồ.

    Hazard không mơ hồ: khớp ở BẤT KỲ dạng nào (kể cả folded/leet) cũng tin.
    Hazard mơ hồ: chỉ tin khi khớp ORIGINAL. "Chỉ khớp folded" xảy ra đúng khi
    original CÓ DẤU mà từ thật khác hazard ("xe của tôi đang chạy" — dấu phân
    biệt nghĩa); còn original KHÔNG dấu thì needle folded khớp thẳng original
    (ORIGINAL) — không dấu là chế độ gõ phổ biến, không được tắt handoff.
    """

    tier = _best_hazard_tier(canonical, hazard)
    if tier is MatchTier.NONE:
        return False
    if hazard in _AMBIGUOUS_HAZARDS:
        return tier is MatchTier.ORIGINAL
    return True


def _critical_safety(canonical: CanonicalText, *, corroboration: bool) -> bool:
    """Hai vế — xe của khách VÀ dấu hiệu nguy hiểm — với corroboration cho
    hazard mơ hồ chỉ khớp folded/leet (original có dấu, từ thật khác hazard)."""

    if not _any_needle_matches(canonical, _OWN_VEHICLE_NEEDLES):
        return False
    for hazard in _CRITICAL_HAZARDS:
        tier = _best_hazard_tier(canonical, hazard)
        if tier is MatchTier.NONE:
            continue
        if hazard in _AMBIGUOUS_HAZARDS:
            if tier is MatchTier.ORIGINAL or corroboration:
                return True
        else:
            return True
    return False


def explicitly_requests_human(user_message: str, canonical: CanonicalText | None = None) -> bool:
    """Khách nói thẳng là muốn gặp người."""

    canonical = canonical or build_canonical_text(user_message)
    return _any_needle_matches(canonical, _HUMAN_REQUEST_NEEDLES)


def is_critical_safety_incident(user_message: str, canonical: CanonicalText | None = None) -> bool:
    """Sự cố nguy hiểm ĐANG xảy ra trên xe của chính khách.

    Cần ĐỦ HAI vế — xe của khách VÀ dấu hiệu nguy hiểm. Chỉ một vế thì không:
    "xe của tôi hết pin" không nguy hiểm, "xe điện có cháy không" không phải sự
    cố. Đây là ranh giới giữa cứu hộ và trả lời câu hỏi.

    Đường thuần keyword không có corroboration: hazard mơ hồ chỉ khớp folded
    không đủ để kết luận — xem `escalation_signals` cho đường có LLM.
    """

    canonical = canonical or build_canonical_text(user_message)
    return _critical_safety(canonical, corroboration=False)


def keyword_severity(user_message: str, canonical: CanonicalText | None = None) -> Severity:
    """Mức khẩn suy từ chữ khách viết, KHÔNG gọi LLM."""

    canonical = canonical or build_canonical_text(user_message)
    if _critical_safety(canonical, corroboration=False):
        return Severity.CRITICAL
    if _any_needle_matches(canonical, _ELEVATED_CONCERN_NEEDLES):
        return Severity.ELEVATED
    return Severity.NORMAL


class EscalationSignals(TypedDict):
    """Unified deterministic and semantic escalation verdict."""

    human_requested: bool
    severity: Severity
    critical_safety: bool


def escalation_signals(
    user_message: str,
    *,
    llm_human_requested: bool = False,
    llm_severity: Severity | str | None = None,
    canonical: CanonicalText | None = None,
) -> EscalationSignals:
    """HỢP tín hiệu keyword và tín hiệu LLM — khớp MỘT nguồn là đủ.

    Hai nguồn hỏng theo hai kiểu khác nhau: danh sách chuỗi trượt câu diễn đạt
    lạ, còn LLM trượt khi bị đánh lạc hướng hoặc khi câu quá ngắn. Lấy HỢP nên
    một nguồn trượt vẫn còn nguồn kia; lấy GIAO thì hai điểm mù cộng lại.

    `canonical` (sinh tại chain) là nguồn so khớp DUY NHẤT — gate không tự
    normalize. Vắng mặt thì tự dựng từ `user_message` (đường tương thích).

    Corroboration cho hazard mơ hồ chỉ khớp folded/leet: LLM CRITICAL hoặc
    human_requested. Có corroboration → handoff CRITICAL; không → không handoff
    (KHÔNG hạ về ELEVATED-thôi).
    """

    canonical = canonical or build_canonical_text(user_message)
    model_level = _coerce_severity(llm_severity)
    corroboration = model_level is Severity.CRITICAL or llm_human_requested
    keyword_level = keyword_severity(user_message, canonical=canonical)
    return {
        "human_requested": llm_human_requested or explicitly_requests_human(user_message, canonical=canonical),
        "severity": _max_severity(keyword_level, model_level),
        "critical_safety": _critical_safety(canonical, corroboration=corroboration) or model_level is Severity.CRITICAL,
    }


_SEVERITY_ORDER: Final[dict[Severity, int]] = {
    Severity.NORMAL: 0,
    Severity.ELEVATED: 1,
    Severity.CRITICAL: 2,
}


def _coerce_severity(value: Severity | str | None) -> Severity:
    if isinstance(value, Severity):
        return value
    if isinstance(value, str):
        try:
            return Severity(value.upper())
        except ValueError:
            return Severity.NORMAL
    return Severity.NORMAL


def _max_severity(left: Severity, right: Severity) -> Severity:
    return left if _SEVERITY_ORDER[left] >= _SEVERITY_ORDER[right] else right


__all__ = [
    "escalation_signals",
    "explicitly_requests_human",
    "is_critical_safety_incident",
    "keyword_severity",
]
