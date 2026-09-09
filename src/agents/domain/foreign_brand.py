"""Khách nhắc tới XE HÃNG KHÁC khi so sánh / hỏi giá.

Catalog chỉ có VinFast — đó là chủ ý. Nhưng "so sánh VF 8 với Tesla Model Y"
đáp "em chưa nắm rõ ý" là nói dối về lý do (đo 2026-08-28). Khách phải nghe đúng
lý do: em chỉ có dữ liệu đã xác minh của VinFast.

Chỉ bắt khi câu VỪA nêu hãng khác VỪA đang so sánh/hỏi giá/thông số. "đang đi
Honda, muốn tư vấn xe điện" là câu MỞ tư vấn, không được chặn — vì thế câu có
động từ tư vấn/mua/chọn thì bỏ qua.
"""

from __future__ import annotations

import re
from typing import Final

from src.agents.domain.canonical_text import CanonicalText, build_canonical_text

_BRANDS: Final[tuple[str, ...]] = (
    "tesla",
    "toyota",
    "honda",
    "hyundai",
    "kia",
    "mazda",
    "ford",
    "byd",
    "mercedes",
    "bmw",
    "audi",
    "lexus",
    "nissan",
    "mitsubishi",
    "suzuki",
    "subaru",
    "volvo",
    "porsche",
    "peugeot",
    "chevrolet",
    "wuling",
    "mg4",
    "mg 4",
    "yadea",
    "pega",
    "dat bike",
    "datbike",
    "dibao",
    "vespa",
    "piaggio",
    "yamaha",
    "sym",
)
_BRAND_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(" + "|".join(re.escape(brand) for brand in sorted(_BRANDS, key=len, reverse=True)) + r")\b"
)
_COMPARE_OR_LOOKUP_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:so\s*sanh|so\s+voi|\bvs\b|gia|bao\s+nhieu|thong\s+so|tot\s+hon|hon\s+hay|nen\s+mua|hay\s+hon)\b"
)
_ADVISORY_VERB: Final[re.Pattern[str]] = re.compile(
    r"\b(?:tu\s*van|mua\s+xe|chon\s+xe|tim\s+xe|doi\s+sang|chuyen\s+sang)\b"
)


def foreign_brand_named(user_message: str, canonical: CanonicalText | None = None) -> str | None:
    """Tên hãng khác trong câu SO SÁNH/HỎI GIÁ, hoặc `None`."""

    canonical = canonical or build_canonical_text(user_message)
    text = canonical.folded
    match = _BRAND_PATTERN.search(text)
    if match is None or _ADVISORY_VERB.search(text) or _COMPARE_OR_LOOKUP_CUE.search(text) is None:
        return None
    return match.group(1)


def foreign_brand_reply(brand: str) -> str:
    """Câu trả lời thẳng lý do, kèm lối đi tiếp."""

    label = brand.title()
    return (
        f"Dạ em chỉ có dữ liệu đã xác minh của xe VinFast nên chưa so sánh hay tra giá được {label} ạ. "
        "Anh/chị cần so sánh hoặc tra cứu mẫu VinFast nào ạ? "
        "Nếu cần trao đổi thêm, em mời tư vấn viên vào cùng ạ."
    )
