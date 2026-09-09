"""Khách hỏi lại điều mình đã nói ("ngân sách tôi là bao nhiêu nhỉ").

Đo 2026-08-28: hai câu như vậy đều nhận "Em chưa nắm rõ ý anh/chị" dù slot vẫn
nằm trong session. Bộ nhớ có, chỉ thiếu cửa đọc ra — cửa đó phải tất định, vì
câu trả lời là dữ liệu của chính khách, không có gì để LLM đoán.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Final

from src.agents.domain.canonical_text import CanonicalText, build_canonical_text

_RECALL_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:toi|anh|chi|minh|em|tui|tao)\s+(?:vua|da|moi)\s+(?:noi|bao|chon|nhap|ke|dua)\b"
    r"|\bcua\s+(?:toi|anh|chi|minh|em)\s+la\s+(?:bao\s+nhieu|gi|the\s+nao|nhu\s+nao)\b"
    r"|\bnhac\s+lai\b|\bem\s+(?:da\s+)?ghi\s+nhan\s+(?:gi|nhung\s+gi|duoc\s+gi)\b"
    r"|\b(?:con\s+)?nho\s+(?:gi|nhung\s+gi)\s+(?:chua|khong)\b"
    r"|\b(?:ngan\s+sach|loai\s+xe|muc\s+dich)\s+(?:toi|anh|chi|minh|em)\s+(?:la\s+)?(?:bao\s+nhieu|gi)\b"
)

_TYPE_LABEL: Final[dict[str, str]] = {"CAR": "ô tô điện", "ELECTRIC_MOTORBIKE": "xe máy điện"}


def is_slot_recall_request(user_message: str, canonical: CanonicalText | None = None) -> bool:
    canonical = canonical or build_canonical_text(user_message)
    return _RECALL_CUE.search(canonical.folded) is not None


def _vnd(value: object) -> str | None:
    try:
        amount = Decimal(str(value))
    except Exception:
        return None
    if amount <= 0:
        return None
    if amount >= 1_000_000_000:
        text = f"{amount / Decimal(1_000_000_000):.2f}".rstrip("0").rstrip(".")
        return f"{text} tỷ"
    return f"{int(amount / Decimal(1_000_000))} triệu"


def recall_reply(known_slots: Mapping[str, object]) -> str:
    """Nhắc lại đúng những gì đã ghi, không thêm không bớt."""

    parts: list[str] = []
    vehicle_type = known_slots.get("vehicle_type")
    if isinstance(vehicle_type, str) and vehicle_type in _TYPE_LABEL:
        parts.append(f"loại xe {_TYPE_LABEL[vehicle_type]}")
    low, high = _vnd(known_slots.get("budget_min_vnd")), _vnd(known_slots.get("budget_max_vnd"))
    if low and high and low != high:
        parts.append(f"ngân sách {low}–{high}")
    elif high or low:
        parts.append(f"ngân sách khoảng {high or low}")
    purpose = known_slots.get("purpose")
    if isinstance(purpose, str) and purpose.strip():
        parts.append(f"mục đích {purpose.strip()}")
    passengers = known_slots.get("passenger_count")
    if isinstance(passengers, int) and passengers > 0:
        parts.append(f"{passengers} người đi cùng")
    distance = known_slots.get("required_range_km")
    if isinstance(distance, (int, float)) and distance > 0:
        parts.append(f"quãng đường khoảng {int(distance)} km mỗi ngày")
    charging = known_slots.get("home_charging")
    if isinstance(charging, bool):
        parts.append("có sạc tại nhà" if charging else "không sạc tại nhà")
    if not parts:
        return "Dạ em chưa ghi nhận thông tin nào của anh/chị ạ."
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f" và {parts[-1]}"
    return f"Dạ em đang ghi nhận: {joined} ạ."
