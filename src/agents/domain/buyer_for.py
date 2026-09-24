"""Khách mua xe cho AI (plan Customer 360 §5.3, `[GIẢ ĐỊNH G8]`).

Luật tách cơ hội R3 cần câu trả lời TẤT ĐỊNH nên đây là regex, không phải LLM.

Bẫy tiếng Việt phải tránh: "chở con đi học" và "cho con" gõ không dấu đều thành
"cho con" — nhưng chở con là MỤC ĐÍCH (xe của chính khách), còn mua cho con là
NGƯỜI ĐƯỢC MUA CHO. Vì vậy:

- Câu CÓ dấu: khớp đúng chữ "cho" (không dấu) — "chở" không bao giờ khớp.
- Câu KHÔNG dấu: chỉ khớp khi có động từ mua/tìm/tư vấn ĐỨNG NGAY TRƯỚC "cho …"
  ("mua cho con"), vì "mua xe cho con di hoc" vẫn có thể là "mua xe chở con".
- "cho gia đình", "cho em/anh/chị" KHÔNG tính: đó là mục đích hoặc đại từ xưng hô.

THUẦN Python.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from enum import StrEnum
from typing import Final


class BuyerFor(StrEnum):
    SELF = "SELF"
    FAMILY = "FAMILY"
    COMPANY = "COMPANY"
    OTHER = "OTHER"


#: "con" còn là loại từ chỉ xe ("báo giá cho con VF 5") — loại khi theo sau là tên/đại từ chỉ xe.
_NOT_VEHICLE: Final = r"(?!\s+(?:vf|xe|evo|feliz|klara|viper|vero|theon|motio|này|nay|đó|do|kia|\d))"
_FAMILY_ACCENTED: Final = (
    rf"(?:con(?:\s+(?:gái|trai))?{_NOT_VEHICLE}|vợ|chồng|bố(?:\s+mẹ)?|mẹ|cha(?:\s+mẹ)?|má|ông\s+bà|bà\s+xã|ông\s+xã)"
)
_FAMILY_PLAIN: Final = (
    rf"(?:con(?:\s+(?:gai|trai))?{_NOT_VEHICLE}|vo|chong|bo(?:\s+me)?|me|cha(?:\s+me)?|ong\s+ba|ba\s+xa|ong\s+xa)"
)
_COMPANY_ACCENTED: Final = r"(?:công\s+ty|doanh\s+nghiệp|cơ\s+quan|văn\s+phòng)"
_COMPANY_PLAIN: Final = r"(?:cong\s+ty|doanh\s+nghiep|co\s+quan|van\s+phong)"
_OTHER_ACCENTED: Final = r"(?:bạn(?:\s+(?:gái|trai|thân))?|người\s+quen|sếp|khách\s+hàng)"
_OTHER_PLAIN: Final = r"(?:ban(?:\s+(?:gai|trai|than))?|nguoi\s+quen|sep|khach\s+hang)"
_VERB_PLAIN: Final = r"(?:mua|tim|chon|tu\s+van|sam|lay|dat)"


def _pattern(target: str, *, accented: bool) -> re.Pattern[str]:
    if accented:
        return re.compile(rf"(?<!\w)cho\s+{target}(?!\w)")
    # Không dấu: bắt buộc động từ mua liền trước (cho phép chen "xe"/"một chiếc xe").
    return re.compile(rf"(?<!\w){_VERB_PLAIN}(?:\s+(?:xe|mot|1|chiec|them)){{0,3}}\s+cho\s+{target}(?!\w)")


_RULES: Final[tuple[tuple[BuyerFor, re.Pattern[str], re.Pattern[str]], ...]] = (
    (BuyerFor.COMPANY, _pattern(_COMPANY_ACCENTED, accented=True), _pattern(_COMPANY_PLAIN, accented=False)),
    (BuyerFor.FAMILY, _pattern(_FAMILY_ACCENTED, accented=True), _pattern(_FAMILY_PLAIN, accented=False)),
    (BuyerFor.OTHER, _pattern(_OTHER_ACCENTED, accented=True), _pattern(_OTHER_PLAIN, accented=False)),
)

#: "tư vấn cho công ty mua xe" cũng là mua cho công ty — nhưng "công ty em cần xe" thì chưa chắc.
_COMPANY_PURCHASE: Final = re.compile(
    rf"(?<!\w){_COMPANY_ACCENTED}\s+(?:\w+\s+){{0,2}}(?:cần\s+mua|muốn\s+mua|mua)(?!\w)"
)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def detect_buyer_for(messages: Iterable[str]) -> BuyerFor:
    """Người được mua cho, từ các câu của KHÁCH trong một phiên. Không thấy dấu hiệu → SELF."""

    for raw in messages:
        text = unicodedata.normalize("NFC", raw).lower()
        has_diacritics = _fold(text) != text
        for buyer, accented, plain in _RULES:
            if (accented if has_diacritics else plain).search(text if has_diacritics else _fold(text)):
                return buyer
        if has_diacritics and _COMPANY_PURCHASE.search(text):
            return BuyerFor.COMPANY
    return BuyerFor.SELF


__all__ = ["BuyerFor", "detect_buyer_for"]
