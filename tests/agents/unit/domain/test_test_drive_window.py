"""Cửa sổ đặt lịch 7 ngày, và payload lượt đầu không được phình.

Kế hoạch chốt: `today … today + 6`, **bao gồm hai đầu**, theo `Asia/Ho_Chi_Minh`.

Hiện `SLOT_DAYS_AHEAD = 3`, `MAX_SLOTS_PER_DAY = 6`, `MAX_SHOWROOMS = 3` → **54
ô**, đo thật trên prod. Bảy ngày × 9 khung × 3 showroom = **189 ô** trong một
lượt chat.

Nên lượt đầu chỉ trả TÓM TẮT theo ngày + khung giờ của đúng ngày mặc định. Đổi
ngày/showroom thì nạp thêm.

Múi giờ là ràng buộc, không phải ghi chú: container prod chạy **UTC**, và đã
dính đúng lỗi này 2026-08-28 — lưới giờ ra 16h–01h giờ khách.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.agents.domain.test_drive import (
    BOOKING_WINDOW_DAYS,
    VIETNAM_TZ,
    booking_window,
    day_summaries,
)


def test_cua_so_dung_bay_ngay_bao_gom_hai_dau() -> None:
    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)

    start, end = booking_window(now=now)

    assert BOOKING_WINDOW_DAYS == 7
    assert start == now.date()
    assert end == now.date() + timedelta(days=6)
    assert (end - start).days + 1 == 7


def test_cua_so_tinh_theo_gio_viet_nam_khong_theo_utc() -> None:
    """Container prod chạy UTC. 23h30 giờ Việt là 16h30 UTC CÙNG ngày, nhưng
    00h30 giờ Việt là 17h30 UTC NGÀY TRƯỚC — lệch một ngày trọn.

    Đã dính đúng lỗi này 2026-08-28: lưới giờ ra 16h–01h.
    """

    late = datetime(2026, 8, 29, 0, 30, tzinfo=VIETNAM_TZ)
    same_moment_utc = late.astimezone(UTC)

    assert same_moment_utc.date() != late.date()
    start, _ = booking_window(now=late)
    assert start == late.date(), "phải lấy ngày theo giờ Việt Nam"


def test_tom_tat_ngay_du_bay_dong() -> None:
    """Lượt đầu trả TÓM TẮT từng ngày, không trả toàn bộ khung giờ."""

    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)

    days = day_summaries(now=now, busy_by_date={})

    assert len(days) == 7
    assert [day.date for day in days][0] == now.date()


def test_ngay_het_cho_duoc_danh_dau_thay_vi_bien_mat() -> None:
    """Ẩn ngày hết chỗ là để khách tự đoán vì sao lịch nhảy cóc."""

    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)
    full_day = now.date() + timedelta(days=2)

    days = day_summaries(now=now, busy_by_date={full_day: 0})

    marked = next(day for day in days if day.date == full_day)
    assert marked.status == "FULL"
    assert marked.available_count == 0
    assert len(days) == 7, "ngày hết chỗ vẫn phải có mặt"


def test_ngay_con_cho_mang_so_khung_con_lai() -> None:
    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)

    days = day_summaries(now=now, busy_by_date={now.date() + timedelta(days=1): 4})

    tomorrow = next(day for day in days if day.date == now.date() + timedelta(days=1))
    assert tomorrow.status == "AVAILABLE"
    assert tomorrow.available_count == 4


def test_ngay_mac_dinh_la_ngay_gan_nhat_con_cho() -> None:
    """Chọn sẵn một ngày đã kín là bắt khách bấm thêm một lần vô ích."""

    from src.agents.domain.test_drive import default_booking_date

    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)
    days = day_summaries(now=now, busy_by_date={now.date(): 0})

    assert default_booking_date(days) == now.date() + timedelta(days=1)


def test_khong_ngay_nao_con_cho_thi_khong_chon_bua() -> None:
    from src.agents.domain.test_drive import default_booking_date

    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)
    days = day_summaries(now=now, busy_by_date={day.date: 0 for day in day_summaries(now=now, busy_by_date={})})

    assert default_booking_date(days) is None


@pytest.mark.parametrize("offset", [-1, 7, 30])
def test_ngay_ngoai_cua_so_bi_tu_choi(offset: int) -> None:
    """Quá khứ và ngày thứ tám trở đi đều nằm ngoài."""

    from src.agents.domain.test_drive import is_within_booking_window

    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)

    assert not is_within_booking_window(now.date() + timedelta(days=offset), now=now)


@pytest.mark.parametrize("offset", [0, 3, 6])
def test_ngay_trong_cua_so_duoc_nhan(offset: int) -> None:
    from src.agents.domain.test_drive import is_within_booking_window

    now = datetime(2026, 8, 28, 10, 0, tzinfo=VIETNAM_TZ)

    assert is_within_booking_window(now.date() + timedelta(days=offset), now=now)
