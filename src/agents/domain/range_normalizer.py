"""Quy đổi quãng đường theo đơn vị thời gian về km/ngày (T2)."""

from __future__ import annotations

import re
from enum import StrEnum
from math import ceil
from typing import Final

MAX_PLAUSIBLE_DAILY_KM = 300


class RangePeriod(StrEnum):
    """Đơn vị thời gian khách dùng khi nói quãng đường."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    TRIP = "trip"


def normalize_range_km(value: int | float | None, period: str | None) -> tuple[int | None, str | None]:
    """Quy đổi `value` km theo `period` về km/ngày.

    Trả `(km_ngay, None)` khi hợp lệ; `(None, lý_do)` khi không thể ghi slot —
    gọi bên ngoài dùng `lý_do` để phát câu xác nhận đơn vị. `None` hoặc đơn vị
    lạ coi là `day`; vượt `MAX_PLAUSIBLE_DAILY_KM` thì từ chối.
    """

    if value is None:
        return None, None
    period = period or RangePeriod.DAY.value
    try:
        normalized = RangePeriod(period)
    except ValueError:
        normalized = RangePeriod.DAY
    if normalized is RangePeriod.TRIP:
        return None, "trip_period_needs_confirmation"
    if normalized is RangePeriod.WEEK:
        daily = ceil(value / 7)
    elif normalized is RangePeriod.MONTH:
        daily = ceil(value / 30)
    else:
        daily = int(value)
    if daily > MAX_PLAUSIBLE_DAILY_KM:
        return None, "daily_km_above_ceiling"
    return daily, None


#: Quãng đường MỖI NGÀY khách nói ra, ở bất kỳ lượt nào.
#:
#: Đòi một con số đi cùng "km" VÀ một chữ chỉ ngày. Thiếu vế "ngày" thì "tầm
#: chạy 400 km" — thông số của xe — bị đọc thành quãng đường khách đi.
#:
#: Chấp cả "mỗi ngày", "1 ngày", "/ngày" và "ngày ... đi ... km": chạy thật trên
#: prod 2026-08-26, khách gõ "ngày em đi 80km, em đăng ký ở Hà Nội" và mẫu cũ —
#: vốn đòi đúng cụm "mỗi ngày" — không khớp, nên `required_range_km` GIỮ NGUYÊN
#: 30 km/ngày của lượt trước. Bảng chi phí vẫn tính theo con số cũ trong khi
#: khách vừa nói con số mới.
_DAILY_KM: Final[re.Pattern[str]] = re.compile(
    r"(?:(?P<truoc>\d{1,4})\s*(?:km|ki\s*lô\s*mét|ki\s*lo\s*met)"
    r"|(?:km|ki\s*lô\s*mét|ki\s*lo\s*met)\s*(?P<sau>\d{1,4}))",
    re.IGNORECASE,
)
_DAY_WORD: Final[re.Pattern[str]] = re.compile(
    r"\b(?:mỗi\s*ngày|moi\s*ngay|hàng\s*ngày|hang\s*ngay|một\s*ngày|mot\s*ngay|1\s*ngày|1\s*ngay|ngày|ngay)\b"
    r"|/\s*ngày|/\s*ngay",
    re.IGNORECASE,
)


#: Lời nói VÔ ĐỊNH KỲ — có chữ "ngày" nhưng KHÔNG phải nhu cầu mỗi ngày.
#:
#: Sếp 2026-08-27: *"nếu khách cung cấp theo ngày [thì cập nhật], còn nếu khách
#: bảo thi thoảng đi bao nhiêu, hay gì đó thì không cập nhật"*.
#:
#: `_DAY_WORD` chấp cả chữ `ngày` TRẦN — cố ý, vì khách thật gõ *"ngày em đi
#: 80km"*. Nhưng cùng chữ đó cũng nằm trong *"thi thoảng có ngày anh chạy
#: 150km"*, và đọc câu ấy thành 150 km/NGÀY là thổi chi phí điện lên gấp mấy
#: lần trên một con số khách chưa từng nói. Gặp cụm ở đây thì BỎ QUA cả lượt:
#: thà giữ giả định cũ còn hơn tính sai rồi bắt khách tự phát hiện.
_OCCASIONAL_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:thi\s*thoảng|thi\s*thoang|thỉnh\s*thoảng|thinh\s*thoang|"
    r"đôi\s*khi|doi\s*khi|lâu\s*lâu|lau\s*lau|thảng\s*hoặc|thang\s*hoac|"
    r"ít\s*khi|it\s*khi|hiếm\s*khi|hiem\s*khi|không\s*thường\s*xuyên|"
    r"khong\s*thuong\s*xuyen|có\s*hôm|co\s*hom|có\s*ngày|co\s*ngay|"
    r"cuối\s*tuần|cuoi\s*tuan|dịp|dip|khi\s*nào\s*rảnh|khi\s*nao\s*ranh)\b",
    re.IGNORECASE,
)


def daily_distance_from_message(user_message: str) -> int | None:
    """Số ki-lô-mét MỖI NGÀY khách vừa nói, hoặc `None`.

    Bản đọc tất định để khách SỬA được giả định bất kỳ lúc nào — xem
    `chain._resolve_daily_distance`. Không có chữ chỉ ngày thì trả `None`: một
    con số km trơ có thể là tầm hoạt động của xe, không phải nhu cầu của khách.
    """

    text = user_message or ""
    if _OCCASIONAL_CUE.search(text) is not None:
        return None
    if _DAY_WORD.search(text) is None:
        return None
    match = _DAILY_KM.search(text)
    if match is None:
        return None
    raw = match.group("truoc") or match.group("sau")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 0 < value <= 2000 else None
