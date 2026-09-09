"""Keep a selected vehicle branch unless the customer explicitly changes it."""

from __future__ import annotations

import re

from src.agents.domain.values import VehicleType

_MOTORBIKE_PATTERN = re.compile(
    r"(xe\s*m[áa]y|x[ée]\s*m[aá]y|motorbike|xe\s*ga|feliz|evo\s*\d*|klara|"
    r"vento|theon|impes|ludo)",
    re.IGNORECASE,
)
_CAR_PATTERN = re.compile(
    r"([ôo]\s*t[ôo]|oto|xe\s*h[ơo]i|[ôo]\s*t[ôo]\s*[đd]i[ệe]n|s[ée]dan|suv|"
    r"vf\s*\d+|\d+\s*ch[ỗo]\b)",
    re.IGNORECASE,
)


def explicit_vehicle_type(user_message: str) -> VehicleType | None:
    """Return only a vehicle type directly supported by the current message."""

    text = " ".join(user_message.split())
    if not text:
        return None
    # KHÔNG đọc "1"/"2" thành loại xe ở đây: hàm này chạy ở mọi lượt, và "2"
    # khách gõ trả lời câu ngân sách bị đổi thành XE MÁY rồi 500 triệu lọc rỗng
    # catalog → đẩy tư vấn viên (đo 2026-08-28). Số thứ tự chỉ có nghĩa khi
    # đang chờ đúng câu hỏi loại xe — tầng pending slot lo việc đó.
    if text.casefold().strip(" .") in {"mot", "oto", "ô tô"}:
        return VehicleType.CAR
    if text.casefold().strip(" .") in {"xe may", "xe máy"}:
        return VehicleType.ELECTRIC_MOTORBIKE
    if _MOTORBIKE_PATTERN.search(text):
        return VehicleType.ELECTRIC_MOTORBIKE
    if _CAR_PATTERN.search(text):
        return VehicleType.CAR
    return None


def keeps_known_vehicle_type(*, known: VehicleType, proposed: VehicleType, user_message: str) -> bool:
    """Return whether an unsupported LLM branch change must be discarded."""

    if known is proposed:
        return False
    return explicit_vehicle_type(user_message) is not proposed
