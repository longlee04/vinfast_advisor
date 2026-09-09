"""Parse Vietnamese number-word amounts ("ba trăm triệu") into integers.

T2 (Evidence-First Lifecycle): guardrail số hiện chỉ thấy ``\\d`` — số viết chữ
"ba trăm triệu" không có digit nào nên lọt qua digit-position check. Parser này
biến dạng chữ thành digit ĐỂ ĐEM đi đối chiếu evidence, đúng bất biến "mọi con số
phải cite + khớp exact" của verification.

Thiết kế (ENG REVIEW AMENDMENT C4):
- Grammar subset TƯỜNG MINH. Ngoài subset → trả ``None`` (fail-closed). Số parse
  SAI (confident wrong) còn nguy hơn không parse, vì nó được đem đối chiếu
  evidence — nên mọi dạng mơ hồ đều trả None.
- Chạy TRÊN chuỗi folded (không dấu) — caller truyền ``canonical.folded``.
- Trigger nằm NGOÀI parser: caller chỉ gọi khi ngữ cảnh giá/tiền.
"""

from __future__ import annotations

import re
from typing import Final

from src.agents.domain.text_normalization import normalize

# Chữ số ở vị trí độc lập (đầu nhóm / đơn vị). "tu"=4, "nam"=5.
_DIGITS: Final[dict[str, int]] = {
    "khong": 0,
    "linh": 0,
    "le": 0,
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "tu": 4,
    "nam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
}
# Chữ số chỉ đứng trước "muoi" (hàng chục) — không có "khong"/"linh".
_TENS_DIGITS: Final[dict[str, int]] = {
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "tu": 4,
    "nam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
}
# Đơn vị sau "muoi"/"mười": "mot"=1 (mốt), "lam"=5 (lăm), "tu"=4 (tư), "nam"=5.
_ONES_AFTER_TEN: Final[dict[str, int]] = {
    "mot": 1,
    "lam": 5,
    "nam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
    "tu": 4,
}
_TRAM = "tram"
_MUOI = "muoi"  # cả "mười" (10, đứng đầu nhóm) lẫn "mươi" (×10, sau digit)
_SCALES: Final[dict[str, int]] = {
    "nghin": 10**3,
    "ngan": 10**3,
    "trieu": 10**6,
    "ty": 10**9,
    "ti": 10**9,
}
_CURRENCY: Final[frozenset[str]] = frozenset({"dong", "vnd", "k", "coc", "cu"})


def _parse_group(words: list[str], i: int) -> tuple[int, int] | None:
    """Parse one sub-thousand group (hundreds/tens/ones) starting at i.

    Returns ``(value, next_i)`` or ``None`` when the tokens at ``i`` do not
    form a valid group (fail-closed).
    """
    start = i
    value = 0

    # Hàng trăm: "ba tram" (300) hoặc "tram" (100).
    if i < len(words) and words[i] == _TRAM:
        value += 100
        i += 1
    elif i + 1 < len(words) and words[i] in _DIGITS and words[i + 1] == _TRAM:
        value += _DIGITS[words[i]] * 100
        i += 2

    # Hàng chục + đơn vị.
    if i < len(words) and words[i] == _MUOI:
        # "mười X" = 10 + X.
        value += 10
        i += 1
        if i < len(words) and words[i] in _ONES_AFTER_TEN:
            value += _ONES_AFTER_TEN[words[i]]
            i += 1
    elif i + 1 < len(words) and words[i] in _TENS_DIGITS and words[i + 1] == _MUOI:
        # "hai mươi X" = 20 + X.
        value += _TENS_DIGITS[words[i]] * 10
        i += 2
        if i < len(words) and words[i] in _ONES_AFTER_TEN:
            value += _ONES_AFTER_TEN[words[i]]
            i += 1
    elif i < len(words) and words[i] in _DIGITS:
        # Đơn vị độc lập ("ba" = 3, "tram" đã xử lý ở trên).
        value += _DIGITS[words[i]]
        i += 1

    if i == start:
        return None
    return value, i


def parse_number_words(tokens: list[str]) -> int | None:
    """Parse a folded token sequence describing a whole-number amount.

    Grammar: ``(<group> <scale>)* <group>`` với scale giảm dần nghiêm ngặt và
    MỌI cặp trừ cặp đầu bắt buộc có scale tường minh. Ví dụ:
    "ba tram trieu" → 300_000_000; "mot ty hai tram trieu" → 1_200_000_000;
    "hai muoi mot trieu" → 21_000_000; "muoi lam trieu" → 15_000_000.
    Bất kỳ token ngoài subset → None (fail-closed).
    """
    if not tokens:
        return None

    # "nua ty" = 500_000_000 (dạng đặc biệt).
    if tokens[0] == "nua" and len(tokens) == 2 and tokens[1] in _SCALES:
        return _SCALES[tokens[1]] // 2

    total = 0
    i = 0
    prev_scale: int | None = None
    groups_seen = 0

    while i < len(tokens):
        group = _parse_group(tokens, i)
        if group is None:
            return None
        value, i = group

        # Đọc scale (nếu có).
        scale = 1
        if i < len(tokens) and tokens[i] in _SCALES:
            scale = _SCALES[tokens[i]]
            i += 1

        # Nhóm sau cặp đầu bắt buộc có scale tường minh, và scale giảm dần.
        if groups_seen > 0 and scale == 1:
            return None
        if prev_scale is not None and scale >= prev_scale:
            return None

        total += value * scale
        prev_scale = scale
        groups_seen += 1

    return total


def parse_amount_from_folded(folded: str) -> int | None:
    """Best-effort parse of a folded amount phrase.

    Returns the amount if it parses cleanly as number words, else ``None``.
    Caller owns trigger gating (price/money context).
    """
    tokens = folded.split()
    if not tokens:
        return None
    while tokens and tokens[-1] in _CURRENCY:
        tokens.pop()
    return parse_number_words(tokens)


def find_number_word_amounts(folded: str) -> list[int]:
    """Return every number-word amount detectable in a folded text.

    Scans for scale/currency anchors ("triệu", "tỷ", "nghìn", "đồng", ...) and,
    for each, walks left to the farthest token that still parses a clean
    amount — so the full number is captured, not a truncated suffix. Only clean
    parses are returned (fail-closed: ambiguous text yields nothing here).
    """
    tokens = folded.split()
    amounts: list[int] = []
    for j, token in enumerate(tokens):
        if token not in _SCALES and token not in _CURRENCY:
            continue
        start = max(0, j - 8)
        for i in range(start, j):
            window = tokens[i : j + 1]
            while window and window[-1] in _CURRENCY:
                window.pop()
            value = parse_number_words(window)
            if value is not None:
                amounts.append(value)
                break
    return amounts


_NUMBER_WORD_TOKEN = (
    r"(?:một|mot|hai|ba|bốn|bon|tư|tu|năm|nam|lăm|lam|sáu|sau|bảy|bay|"
    r"tám|tam|chín|chin|mười|mươi|muoi|mốt|trăm|tram|nửa|nua|linh|lẻ|le|không|khong)"
)
_SCALE_OR_CURRENCY = r"(?:nghìn|nghin|ngàn|ngan|triệu|trieu|tỷ|ty|tỉ|ti|đồng|dong|vnd)"
#: Cụm số-viết-chữ: 1..8 token số tiếng Việt (có dấu lẫn không dấu), bắt buộc kết
#: thúc bằng đơn vị scale hoặc tiền tệ để tránh bắt nhầm "năm" (thời gian).
_NUMBER_WORD_PHRASE: Final[re.Pattern[str]] = re.compile(
    rf"\b(?:{_NUMBER_WORD_TOKEN}\s+){{1,8}}{_SCALE_OR_CURRENCY}\b",
    re.IGNORECASE,
)


def replace_number_words(text: str) -> str:
    """Rewrite number-word amounts as digits so downstream digit checks apply.

    Operates on the ORIGINAL (diacritics-preserved) text so citation markers
    like ``[evidence_id:...]`` survive untouched. "sáu trăm chín mươi triệu" →
    "690000000". Only clean parses are replaced; anything outside the grammar
    subset is left alone (fail-closed: no digits appear, the digit check then
    rejects nothing there, which is the caller's safe default).
    """

    def _repl(match: re.Match[str]) -> str:
        phrase = match.group(0)
        folded = normalize(phrase)
        value = parse_amount_from_folded(folded)
        if value is not None:
            return str(value)
        return phrase

    return _NUMBER_WORD_PHRASE.sub(_repl, text)
