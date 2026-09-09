"""Mã khung giờ phải là GIẤY PHÉP do server cấp, không phải một chuỗi đọc được.

Lỗ hổng thật (rà soát 2026-08-28, mức HIGH). Mã cũ là chữ thường:

    __lichlaithu__|2026-08-30T14:00:00+07:00|VinFast Long Biên

`decode_slot_choice` chỉ tách chuỗi rồi `chain._book_test_drive` ghi thẳng vào
`test_drive_bookings`. Ai cũng tự gõ được một mã như vậy — showroom bịa, giờ đã
qua, giờ ngoài cửa sổ bảy ngày, hoặc showroom chưa từng được mời cho phiên đó.
Endpoint availability trả mã do server sinh là đúng hướng, nhưng chừng nào mã
còn giả được thì nó vẫn chưa phải một giấy phép.

Nên mã giờ mang chữ ký HMAC và **buộc vào** phiên, khách, showroom, mốc giờ và
một hạn dùng. Sửa một byte là chữ ký hỏng; mượn mã của phiên khác là sai ràng
buộc; để quá hạn là hết hiệu lực.

KHÔNG buộc `vehicle_id`: endpoint availability không biết xe nào, và xe được đọc
từ chặng sau đề xuất ở phía server — client không chọn được nó.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.agents.domain.test_drive import VIETNAM_TZ
from src.agents.domain.test_drive_booking import decode_slot_choice, encode_slot_choice

SECRET = b"khoa-ky-cho-test"
KHAC = b"khoa-khac-hoan-toan"
NOW = datetime(2026, 8, 28, 9, 0, tzinfo=VIETNAM_TZ)
KHI = datetime(2026, 8, 30, 14, 0, tzinfo=VIETNAM_TZ)
PHIEN = "11111111-1111-1111-1111-111111111111"
KHACH = "customer-1"


def _token(**overrides) -> str:
    kwargs = {
        "showroom": "VinFast Long Biên",
        "scheduled_at": KHI,
        "session_id": PHIEN,
        "customer_id": KHACH,
        "issued_at": NOW,
        "secret": SECRET,
    }
    kwargs.update(overrides)
    return encode_slot_choice(**kwargs)


def _read(token: str, **overrides):
    kwargs = {"session_id": PHIEN, "customer_id": KHACH, "now": NOW, "secret": SECRET}
    kwargs.update(overrides)
    return decode_slot_choice(token, **kwargs)


def test_ma_do_server_cap_thi_doc_lai_dung_nguyen() -> None:
    choice = _read(_token())

    assert choice is not None
    assert choice.showroom == "VinFast Long Biên"
    assert choice.scheduled_at == KHI


def test_sua_mot_ky_tu_la_ma_hong() -> None:
    """Không có phép "sửa nhẹ": mọi thay đổi đều làm chữ ký sai."""

    token = _token()
    hong = token[:-1] + ("a" if token[-1] != "a" else "b")

    assert _read(hong) is None


def test_tu_go_ma_bang_tay_thi_khong_dat_duoc() -> None:
    """Đúng cái mã của bản cũ — giờ phải bị từ chối."""

    assert _read("__lichlaithu__|2026-08-30T14:00:00+07:00|Showroom Bia Dat") is None


def test_khoa_khac_thi_khong_ky_ho_duoc() -> None:
    assert _read(_token(secret=KHAC)) is None


def test_ma_cua_phien_khac_khong_dung_duoc_o_phien_nay() -> None:
    """Mượn mã của phiên khác là sai ràng buộc, dù chữ ký vẫn thật."""

    assert _read(_token(session_id="22222222-2222-2222-2222-222222222222")) is None


def test_ma_cua_khach_khac_khong_dung_duoc() -> None:
    assert _read(_token(customer_id="customer-2")) is None


def test_qua_han_thi_het_hieu_luc() -> None:
    """Giấy phép có hạn — mã nhặt được từ log cũ không dùng lại được mãi.

    Hạn tính từ lúc CẤP, không phải từ giờ hẹn: một mã cấp hôm nay cho khung giờ
    tuần sau vẫn phải hết hạn trước khi tuần sau tới.
    """

    token = _token()

    assert _read(token, now=NOW + timedelta(days=30)) is None
    assert _read(token, now=NOW + timedelta(minutes=30)) is not None


@pytest.mark.parametrize("rac", ["", "xin chao", "__lichlaithu__", "__lichlaithu__|", "__lichlaithu__|a|b|c"])
def test_chuoi_rac_tra_none_chu_khong_no(rac: str) -> None:
    assert _read(rac) is None


def test_ma_khong_lo_ten_showroom_ra_khung_chat() -> None:
    """Payload mã hoá base64 — log và khung chat không đọc thẳng ra được.

    Không phải bí mật, nhưng một chuỗi trông như dữ liệu thì không ai bị dụ
    "sửa tay cho nhanh".
    """

    assert "Long Biên" not in _token()


def test_ma_cap_o_tuong_lai_bi_tu_choi() -> None:
    """Chỉ chặn mã QUÁ CŨ là hở một nửa.

    `now - issued_at > TTL` cho hiệu số ÂM khi `issued_at` nằm ở tương lai, nên
    một mã ghi ngày mai vẫn qua cửa — và nó sống dài hơn TTL thật đúng bằng
    khoảng lệch đó. Cửa phải chặn cả hai đầu.
    """

    assert _read(_token(issued_at=NOW + timedelta(hours=5)), now=NOW) is None


def test_lech_dong_ho_nho_van_chap_nhan() -> None:
    """Hai máy lệch nhau vài giây là chuyện thường — không phải tấn công.

    Chặn cứng `issued_at <= now` sẽ làm rơi những mã hợp lệ do máy cấp chạy
    nhanh hơn máy đọc vài giây.
    """

    assert _read(_token(issued_at=NOW + timedelta(seconds=30)), now=NOW) is not None


def test_bien_cua_han_dung_hai_gio() -> None:
    """Chốt ĐÚNG mép: đúng 2 giờ còn nhận, quá một giây là hết.

    Không có ca biên thì một lần đổi `>` thành `>=` (hoặc ngược lại) trôi qua mà
    không ai thấy — và nó dịch hạn của mọi giấy phép đi một nhịp.
    """

    token = _token()

    assert _read(token, now=NOW + timedelta(hours=2)) is not None
    assert _read(token, now=NOW + timedelta(hours=2, seconds=1)) is None


def test_bien_cua_lech_dong_ho_dung_hai_phut() -> None:
    """Cửa phía tương lai cũng phải có mép rõ."""

    assert _read(_token(issued_at=NOW + timedelta(minutes=2)), now=NOW) is not None
    assert _read(_token(issued_at=NOW + timedelta(minutes=2, seconds=1)), now=NOW) is None
