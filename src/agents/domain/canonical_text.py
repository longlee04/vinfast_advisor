"""CanonicalText — ba dạng chuẩn hoá của một câu, sinh MỘT lần mỗi lượt.

Gốc của 4/12 vết nứt trong luồng agent là "hai cổng chấm hai phiên bản chuỗi":
escalation đọc chuỗi bỏ dấu, quote_risk đọc chuỗi có dấu, và không nơi nào bắt
được cách điệu `b0c ch4y`. Module này là nguồn sự thật DUY NHẤT cho mọi gate
keyword (escalation, quote_risk, blocklist):

- `original` — giữ dấu, hạ thường, gộp khoảng trắng. Dùng để phân biệt nghĩa
  nhờ dấu ("đang chạy" ≠ "đang cháy").
- `folded` — bỏ dấu, chỉ chữ và số (chính là `text_normalization.normalize`).
  Dùng cho entity/fuzzy-match tên xe (GIỮ số, tránh "vf5"→"vfs") và cho khớp
  keyword không dấu.
- `leet_decoded` — map digit→chữ gần hình (0→o, 4→a, 1→i, 3→e, 5→s, 7→t) rồi
  fold. Dùng cho keyword gate để bắt cách điệu "b0c ch4y" → "boc chay".

`compile_keyword_variants` + `match_tier` là bộ so khớp dùng chung cho ba
consumer. Variants được compile ở module-load, không mỗi lượt.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.text_normalization import normalize

#: Bảng leet: digit → chữ gần hình. "b0c ch4y" → "boc chay" → fold → "boc chay".
_LEET_TRANSLATION: Final[dict[int, str]] = {
    ord("0"): "o",
    ord("4"): "a",
    ord("1"): "i",
    ord("3"): "e",
    ord("5"): "s",
    ord("7"): "t",
}

#: Dấu câu/ký tự lạ → khoảng trắng, GIỮ chữ Unicode có dấu (khác `normalize`
#: bỏ dấu): "cháy!!" phải thành "cháy" chứ không phải "chay".
_ORIGINAL_PUNCTUATION: Final[re.Pattern[str]] = re.compile(r"[^\w\s]+", re.UNICODE)


class MatchTier(StrEnum):
    """Mức tin cậy của một lần khớp keyword trên canonical.

    ORIGINAL > FOLDED > LEET > NONE. ORIGINAL nghĩa là needle khớp trên dạng
    giữ dấu — dấu là thông tin phân biệt nghĩa duy nhất còn lại sau khi fold.
    """

    ORIGINAL = "ORIGINAL"
    FOLDED = "FOLDED"
    LEET = "LEET"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class CanonicalText:
    """Ba dạng chuẩn hoá của cùng một câu, bất biến sau khi sinh."""

    original: str
    folded: str
    leet_decoded: str

    @classmethod
    def from_state(cls, state: Mapping[str, object]) -> CanonicalText:
        """Dựng từ ba field `canonical_*` trong AgentState — node không tự sinh.

        State thiếu field (test double, graph cũ) → canonical rỗng, gate chấm
        không khớp gì — fail-closed, không tự normalize bù.
        """

        return cls(
            original=str(state.get("canonical_original") or ""),
            folded=str(state.get("canonical_folded") or ""),
            leet_decoded=str(state.get("canonical_leet_decoded") or ""),
        )


def _original_form(text: str) -> str:
    """Dạng giữ dấu: NFC, bỏ dấu câu, hạ thường, gộp khoảng trắng — KHÔNG bỏ dấu."""

    if not text:
        return ""
    cleaned = _ORIGINAL_PUNCTUATION.sub(" ", unicodedata.normalize("NFC", text))
    return " ".join(cleaned.casefold().split())


def _leet_decode(text: str) -> str:
    """Thay digit bằng chữ gần hình theo bảng leet."""

    return text.translate(_LEET_TRANSLATION)


def build_canonical_text(text: str) -> CanonicalText:
    """Sinh ba dạng canonical cho một câu. Chuỗi rỗng/None-safe."""

    if not text:
        return CanonicalText(original="", folded="", leet_decoded="")
    return CanonicalText(
        original=_original_form(text),
        folded=normalize(text),
        leet_decoded=normalize(_leet_decode(text)),
    )


def compile_keyword_variants(keywords: Iterable[str]) -> tuple[str, ...]:
    """Fold + dedupe danh sách keyword thành tuple needle để match trên canonical.

    Mỗi keyword sinh hai needle: dạng giữ dấu (để khớp `original`) và dạng bỏ
    dấu (để khớp `folded`/`leet_decoded`). Keyword đã không dấu thì hai dạng
    trùng nhau — dedupe giữ tuple gọn. Compile ở module-load, không mỗi lượt.
    """

    seen: set[str] = set()
    result: list[str] = []
    for keyword in keywords:
        for form in (_original_form(keyword), normalize(keyword)):
            if form and form not in seen:
                seen.add(form)
                result.append(form)
    return tuple(result)


def _word_contains(haystack: str, needle: str) -> bool:
    """Khớp `needle` theo RANH GIỚI TỪ, không phải chuỗi con.

    `"chay" in "xe cua toi chay tot"` là True, và đó chính là báo động giả cần
    chặn. Bọc hai đầu bằng khoảng trắng biến phép so khớp thành theo từ, giữ
    nguyên khả năng khớp cụm nhiều từ ("boc chay", "mat phanh").
    """

    if not haystack or not needle:
        return False
    return f" {needle} " in f" {haystack} "


def match_tier(canonical: CanonicalText, needle: str) -> MatchTier:
    """Tier khớp cao nhất của `needle` trên `canonical`.

    Thứ tự ưu tiên: original (giữ dấu) → folded → leet_decoded. Needle có thể
    là dạng có dấu hoặc không dấu (sinh từ `compile_keyword_variants`); nó khớp
    `original` khi chính xác dạng giữ dấu xuất hiện, khớp `folded`/`leet` khi
    dạng bỏ dấu xuất hiện.
    """

    if _word_contains(canonical.original, needle):
        return MatchTier.ORIGINAL
    if _word_contains(canonical.folded, needle):
        return MatchTier.FOLDED
    if _word_contains(canonical.leet_decoded, needle):
        return MatchTier.LEET
    return MatchTier.NONE


__all__ = [
    "CanonicalText",
    "MatchTier",
    "build_canonical_text",
    "compile_keyword_variants",
    "match_tier",
]
