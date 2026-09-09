"""Lượt đầu chỉ chở khung giờ của MỘT ngày; ngày khác nạp sau.

Nới cửa sổ từ 3 lên 7 ngày mà không đổi cách gửi thì thẻ **nặng hơn trước**: 54 ô
hôm nay thành tối đa 189. Đó là lý do bước này chặn deploy, không phải một tối ưu
để dành.

Hợp đồng: `build_test_drive_card(..., only_date=...)` chỉ dựng ô của ngày được
chọn, còn `days` vẫn liệt kê ĐỦ bảy ngày để khách thấy mình chọn được những ngày
nào.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.agents.domain.test_drive import VIETNAM_TZ
from src.agents.services.test_drive import ShowroomSlots, build_test_drive_card

NOW = datetime(2026, 8, 28, 8, 0, tzinfo=VIETNAM_TZ)


def _slots_over_days(days: int, per_day: int = 6) -> tuple[datetime, ...]:
    return tuple(
        NOW.replace(hour=9 + hour) + timedelta(days=offset)
        for offset in range(days)
        for hour in range(per_day)
    )


def _row(name: str, slots: tuple[datetime, ...]) -> ShowroomSlots:
    return ShowroomSlots(
        showroom_id=f"sr-{name}",
        showroom_name=name,
        address=f"Địa chỉ {name}",
        distance_km=2.0,
        slots=slots,
    )


def _issue(showroom: str, when) -> str:
    """Giấy phép giả cho test THUẦN: đủ để phân biệt ô, không cần khoá thật."""

    return f"__ky__|{showroom}|{when.isoformat()}"


def _card(only_date=None):
    rows = [_row("A", _slots_over_days(7)), _row("B", _slots_over_days(7)), _row("C", _slots_over_days(7))]
    return build_test_drive_card("VinFast VF 5 All New", rows, issue=_issue, only_date=only_date)


def test_khong_gioi_han_ngay_thi_the_phinh_len() -> None:
    """Ghi lại con số biện minh — để không ai quay đầu vì thấy code phức tạp hơn."""

    card = _card()

    assert card is not None
    assert len(card.options) > 100, f"gửi hết là {len(card.options)} ô"


def test_gioi_han_mot_ngay_thi_the_gon_lai() -> None:
    card = _card(only_date=NOW.date())

    assert card is not None
    assert len(card.options) <= 6 * 3


def test_van_liet_ke_du_bay_ngay_de_khach_biet_chon_duoc_gi() -> None:
    """Cắt ô giờ KHÔNG được cắt luôn danh sách ngày.

    Khách phải thấy mình chọn được những ngày nào; thiếu nó thì "nạp lười" biến
    thành "chỉ có một ngày".
    """

    card = _card(only_date=NOW.date())

    assert card is not None
    assert len(card.days) == 7


def test_o_gio_deu_thuoc_dung_ngay_da_chon() -> None:
    day_two = NOW.date() + timedelta(days=1)

    card = _card(only_date=day_two)

    assert card is not None
    assert {option.scheduled_at.date() for option in card.options} == {day_two}


def test_ngay_mac_dinh_la_ngay_duoc_chon() -> None:
    day_three = NOW.date() + timedelta(days=2)

    card = _card(only_date=day_three)

    assert card is not None
    assert card.default_date == day_three.isoformat()
