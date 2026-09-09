"""Luật thuần của lượt gợi ý showroom + khung giờ đặt lịch lái thử.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK. Chỉ sinh
lưới giờ và định dạng hiển thị; việc đọc showroom gần và đếm giờ đã đặt nằm ở
tầng service, không nằm ở đây.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone
from typing import Final

from src.agents.domain.pending_slot import PendingSlotRequest

#: Giờ Việt Nam, ĐÓNG CỨNG — không đọc giờ tiến trình.
#:
#: BUG THẬT đo trên prod 2026-08-28: container backend chạy UTC (`TZ` không đặt),
#: mà `datetime.now().astimezone()` lấy đúng giờ tiến trình. Showroom mở 09:00
#: theo giờ Việt Nam, nên lưới sinh ra 9h–18h UTC = 16h–01h giờ khách — mời khách
#: tới lái thử lúc một giờ sáng. Nhãn ngày lệch theo: khung 28/08 bị gọi là "ngày
#: mai" trong khi ở Việt Nam đã sang 28/08 rồi.
#:
#: Không dùng `ZoneInfo("Asia/Ho_Chi_Minh")`: Việt Nam không đổi giờ mùa, nên một
#: độ lệch cố định là ĐỦ và không phụ thuộc gói dữ liệu múi giờ có trong image hay không.
VIETNAM_TZ: Final[timezone] = timezone(timedelta(hours=7))

DEFAULT_OPEN_HOUR: Final[int] = 9
DEFAULT_CLOSE_HOUR: Final[int] = 18
SLOT_INTERVAL_MINUTES: Final[int] = 60
#: GIỮ LẠI cho mã cũ còn tham chiếu; lưới giờ nay dùng `BOOKING_WINDOW_DAYS`.
SLOT_DAYS_AHEAD: Final[int] = 3

#: Cửa sổ đặt lịch: `today … today + 6`, **bao gồm hai đầu** — đúng 7 ngày.
#:
#: Tính theo GIỜ VIỆT NAM, không theo giờ container. Prod chạy UTC, và
#: 00h30 giờ Việt là 17h30 UTC NGÀY TRƯỚC — lệch trọn một ngày. Đã dính đúng lỗi
#: này 2026-08-28: lưới giờ ra 16h–01h giờ khách.
BOOKING_WINDOW_DAYS: Final[int] = 7
MAX_SHOWROOMS: Final[int] = 3

#: Intent của bản ghi chờ khi khách xin lái thử mà chưa nêu mẫu nào.
#:
#: Chuỗi riêng chứ không mượn một thành viên `Intent`: `Intent` là nhãn cho bộ
#: trích ý của LLM, và nó KHÔNG có `TEST_DRIVE` — thêm vào đó để dùng ở đây là
#: mở cho LLM một nhãn nó chưa từng được dạy phát.
TEST_DRIVE_INTENT: Final[str] = "TEST_DRIVE"
#: Slot đang chờ: tên mẫu xe khách muốn lái thử.
TEST_DRIVE_VEHICLE_SLOT: Final[str] = "test_drive_vehicle"
#: Trần số NÚT khung giờ dựng cho một lượt (Sếp 2026-08-26). Mỗi khung là một
#: nút, mà một màn chat đầy nút thì khách không chọn nổi — và khung đầu bao giờ
#: cũng là khung gần nhất.
MAX_BUTTON_SLOTS: Final[int] = 6
MAX_SLOTS_PER_DAY: Final[int] = 6


@dataclass(frozen=True, slots=True)
class ShowroomSlots:
    """Một showroom gợi ý kèm các giờ trống đã lọc."""

    showroom_id: str
    showroom_name: str
    address: str
    distance_km: float | None
    slots: tuple[datetime, ...]
    #: Toạ độ showroom (đợt 9) — mặc định `None` để mọi chỗ dựng cũ không đổi.
    latitude: float | None = None
    longitude: float | None = None


def pending_for_test_drive_vehicle(*, user_message: str, asked_at: datetime) -> PendingSlotRequest:
    """Bản ghi chờ cho câu hỏi "anh/chị muốn lái thử mẫu nào".

    Hỏi mà KHÔNG mở bản ghi chờ là hỏi xong quên ngay: lượt sau khách gõ "VF 5"
    trơ trọi, và không còn dấu vết nào cho biết hai chữ đó đang trả lời câu gì —
    nó chạy vào nhánh tra cứu và khách nhận về bảng thông số thay vì khung giờ.

    Giữ nguyên câu gốc trong `partial_form`: `services/test_drive` cần nó để dựng
    lại pending vị trí ở bước sau, và lúc đó lượt hỏi tên xe đã trôi qua.
    """

    return PendingSlotRequest(
        intent=TEST_DRIVE_INTENT,
        missing_slot=TEST_DRIVE_VEHICLE_SLOT,
        partial_form={"original_message": user_message},
        asked_at=asked_at,
    )


def now_in_vietnam() -> datetime:
    """Bây giờ, theo giờ khách — nguồn thời gian duy nhất của luồng đặt lịch."""

    return datetime.now(tz=VIETNAM_TZ)


def parse_business_hours(open_time: str | None, close_time: str | None) -> tuple[int, int]:
    """Giờ mở/đóng dạng "HH:MM" về (giờ_mở, giờ_đóng); hỏng thì về mặc định 9–18."""

    def _hour(value: str | None, fallback: int) -> int:
        if not value:
            return fallback
        head = value.strip().split(":", 1)[0]
        if not head.isdigit():
            return fallback
        hour = int(head)
        return hour if 0 <= hour <= 23 else fallback

    open_hour = _hour(open_time, DEFAULT_OPEN_HOUR)
    close_hour = _hour(close_time, DEFAULT_CLOSE_HOUR)
    if close_hour <= open_hour:
        close_hour = DEFAULT_CLOSE_HOUR
    return open_hour, close_hour


def candidate_slots(*, open_time: str | None, close_time: str | None, now: datetime) -> tuple[datetime, ...]:
    """Lưới giờ cho vài ngày tới, bỏ giờ đã qua của ngày hôm nay."""

    open_hour, close_hour = parse_business_hours(open_time, close_time)
    slots: list[datetime] = []
    # `BOOKING_WINDOW_DAYS` chứ không `SLOT_DAYS_AHEAD`: lịch bày ra bảy ngày thì
    # cả bảy phải có khung. Ba ngày là một cửa sổ hứa nhiều hơn thứ nó có —
    # khách bấm sang ngày thứ tư và thấy trống trơn.
    for day_offset in range(BOOKING_WINDOW_DAYS):
        day = (now + timedelta(days=day_offset)).date()
        for hour in range(open_hour, close_hour):
            candidate = datetime.combine(day, time(hour=hour), tzinfo=now.tzinfo)
            if candidate <= now:
                continue
            slots.append(candidate)
    return tuple(slots)


def format_slot(value: datetime) -> str:
    """Một giờ dạng "9h00", "14h00"."""

    return f"{value.hour}h00"


def format_date(value: datetime, *, today: datetime | None = None) -> str:
    """Ngày dạng "hôm nay", "ngày mai", "ngày 26/08"."""

    base = today or datetime.now(tz=value.tzinfo)
    if value.date() == base.date():
        return "hôm nay"
    if value.date() == (base + timedelta(days=1)).date():
        return "ngày mai"
    return f"ngày {value.strftime('%d/%m')}"


def format_day_label(value: datetime, *, today: datetime | None = None) -> str:
    """Nhãn tab ngày: "Hôm nay 28/08", "Ngày mai 29/08", "30/08".

    Luôn KÈM ngày tháng, kể cả với "hôm nay": khách mở lại tin nhắn cũ vào sáng
    hôm sau vẫn phải đọc ra được mình đã hẹn ngày nào. Chữ "hôm nay" trong một
    tin nhắn của quá khứ là chữ nói dối.
    """

    base = today or datetime.now(tz=value.tzinfo)
    day_month = value.strftime("%d/%m")
    if value.date() == base.date():
        return f"Hôm nay {day_month}"
    if value.date() == (base + timedelta(days=1)).date():
        return f"Ngày mai {day_month}"
    return day_month


@dataclass(frozen=True, slots=True)
class DaySummary:
    """Tóm tắt một ngày trong cửa sổ — KHÔNG chở khung giờ.

    Lượt đầu chỉ gửi tóm tắt: 7 ngày × 9 khung × 3 showroom là **189 ô** trong
    một lượt chat, trong khi hiện tại đã là 54. Khung giờ của ngày nào thì nạp
    khi khách chọn ngày đó.
    """

    date: date_type
    status: str
    available_count: int


def booking_window(*, now: datetime | None = None) -> tuple[date_type, date_type]:
    """Ngày đầu và ngày cuối của cửa sổ, theo giờ Việt Nam, bao gồm hai đầu."""

    moment = (now or now_in_vietnam()).astimezone(VIETNAM_TZ)
    start = moment.date()
    return start, start + timedelta(days=BOOKING_WINDOW_DAYS - 1)


def is_within_booking_window(day: date_type, *, now: datetime | None = None) -> bool:
    """Ngày quá khứ và ngày thứ tám trở đi đều nằm NGOÀI."""

    start, end = booking_window(now=now)
    return start <= day <= end


def day_summaries(
    *,
    now: datetime | None = None,
    busy_by_date: Mapping[date_type, int],
) -> tuple[DaySummary, ...]:
    """Bảy dòng tóm tắt, kể cả ngày đã kín.

    Ngày hết chỗ vẫn có mặt, đánh dấu `FULL`. Ẩn nó đi là để khách tự đoán vì sao
    lịch nhảy cóc — và đoán sai theo chiều "chắc hệ thống lỗi".
    """

    start, _ = booking_window(now=now)
    summaries: list[DaySummary] = []
    for offset in range(BOOKING_WINDOW_DAYS):
        day = start + timedelta(days=offset)
        remaining = busy_by_date.get(day, MAX_SLOTS_PER_DAY)
        summaries.append(
            DaySummary(
                date=day,
                status="AVAILABLE" if remaining > 0 else "FULL",
                available_count=remaining,
            )
        )
    return tuple(summaries)


def default_booking_date(days: Sequence[DaySummary]) -> date_type | None:
    """Ngày gần nhất CÒN CHỖ, hoặc `None` khi cả cửa sổ đã kín.

    Chọn sẵn một ngày đã kín là bắt khách bấm thêm một lần vô ích; chọn bừa khi
    không còn ngày nào là nói dối họ.
    """

    return next((day.date for day in days if day.available_count > 0), None)


def initial_slot_budget() -> int:
    """Trần số ô giờ được phép có trong LƯỢT ĐẦU.

    Một ngày × số showroom — KHÔNG nhân với bảy. Bảy ngày × 9 khung × 3 showroom
    là 189 ô trong một lượt chat, trong khi thẻ hiện tại đã chở 54 (đo thật trên
    prod 2026-08-28).

    Ngày khác nạp khi khách chọn. `len(options)` vì vậy không còn dùng làm mốc
    được: sau khi nạp lười nó chỉ còn là tóm tắt.
    """

    return MAX_SLOTS_PER_DAY * MAX_SHOWROOMS
