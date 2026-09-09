"""Payload lượt đầu KHÔNG được phình khi mở cửa sổ 7 ngày.

Đo thật trên prod 2026-08-28: thẻ hiện tại chở **54 ô** (3 ngày × 6 khung × 3
showroom). Bảy ngày × 9 khung × 3 showroom là **189 ô** trong một lượt chat.

Nên hợp đồng đổi: lượt đầu chở **tóm tắt 7 ngày** + khung giờ của **đúng ngày
mặc định**. Đổi ngày hay đổi showroom thì nạp thêm.

`len(options)` KHÔNG dùng làm mốc được nữa — sau khi nạp lười nó chỉ còn là tóm
tắt, và 54 hôm nay không so được với số sau. Bộ này đo đúng thứ cần chặn: **số ô
giờ có trong lượt đầu**.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.agents.domain.test_drive import (
    BOOKING_WINDOW_DAYS,
    MAX_SHOWROOMS,
    MAX_SLOTS_PER_DAY,
    VIETNAM_TZ,
    day_summaries,
    initial_slot_budget,
)

NOW = datetime(2026, 8, 28, 8, 0, tzinfo=VIETNAM_TZ)


def test_gui_het_bay_ngay_la_gan_hai_tram_o() -> None:
    """Con số biện minh cho việc nạp lười — ghi lại để không ai quay đầu."""

    naive = BOOKING_WINDOW_DAYS * MAX_SLOTS_PER_DAY * MAX_SHOWROOMS

    assert naive >= 100, f"gửi hết là {naive} ô"


def test_luot_dau_chi_cho_khung_gio_cua_mot_ngay() -> None:
    """Trần = một ngày × số showroom, không nhân với bảy."""

    budget = initial_slot_budget()

    assert budget == MAX_SLOTS_PER_DAY * MAX_SHOWROOMS
    assert budget < BOOKING_WINDOW_DAYS * MAX_SLOTS_PER_DAY * MAX_SHOWROOMS


def test_tom_tat_ngay_re_hon_han_khung_gio() -> None:
    """Bảy dòng tóm tắt, không phải 189 ô."""

    days = day_summaries(now=NOW, busy_by_date={})

    assert len(days) == BOOKING_WINDOW_DAYS
    assert len(days) < initial_slot_budget()


@pytest.mark.parametrize("offset", [0, 1, 6])
def test_moi_ngay_trong_cua_so_deu_nap_them_duoc(offset: int) -> None:
    from src.agents.domain.test_drive import is_within_booking_window

    assert is_within_booking_window(NOW.date() + timedelta(days=offset), now=NOW)


def test_luoi_gio_phu_dung_cua_so_bay_ngay() -> None:
    """`candidate_slots` phải sinh cho CẢ cửa sổ, không dừng ở ba ngày.

    Trước bản này `SLOT_DAYS_AHEAD = 3`: khách mở lịch thấy 7 ngày nhưng bốn ngày
    cuối không bao giờ có khung nào — một cửa sổ hứa nhiều hơn thứ nó có.
    """

    from src.agents.domain.test_drive import candidate_slots

    slots = candidate_slots(open_time="09:00", close_time="18:00", now=NOW)
    days = {slot.date() for slot in slots}

    assert len(days) == BOOKING_WINDOW_DAYS
    assert max(days) == NOW.date() + timedelta(days=BOOKING_WINDOW_DAYS - 1)


def test_khung_gio_da_qua_trong_hom_nay_van_bi_loai() -> None:
    """Mở cửa sổ rộng ra KHÔNG được làm mất chốt bỏ giờ đã trôi qua."""

    from src.agents.domain.test_drive import candidate_slots

    noon = NOW.replace(hour=12)
    slots = candidate_slots(open_time="09:00", close_time="18:00", now=noon)

    assert all(slot > noon for slot in slots)
