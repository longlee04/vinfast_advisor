"""Chốt khung giờ lái thử bằng NÚT, không bằng chữ tự do.

Sếp 2026-08-26: "nối luôn đăng ký lái thử". Bước chốt lịch là chỗ **không được
đoán**: sai một giờ là khách tới showroom vào lúc không ai đợi, sai showroom thì
họ đi nhầm thành phố.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agents.domain.test_drive_booking import (
    decode_slot_choice,
    encode_slot_choice,
    wants_test_drive,
)

WHEN = datetime(2026, 8, 27, 15, 0, tzinfo=UTC)
CAP_LUC = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)
SECRET = b"khoa-ky-cho-test"
PHIEN = "11111111-1111-1111-1111-111111111111"
KHACH = "customer-1"


def _cap(showroom: str, scheduled_at: datetime = WHEN) -> str:
    """Cấp giấy phép thật cho một khung — phép ký ở `test_slot_token.py`."""

    return encode_slot_choice(
        showroom=showroom,
        scheduled_at=scheduled_at,
        session_id=PHIEN,
        customer_id=KHACH,
        issued_at=CAP_LUC,
        secret=SECRET,
    )


def _doc(message: str):
    return decode_slot_choice(
        message, session_id=PHIEN, customer_id=KHACH, now=CAP_LUC, secret=SECRET
    )


@pytest.mark.parametrize(
    "showroom",
    [
        "VinFast Long Biên",
        # Địa chỉ thật đầy dấu phẩy và gạch ngang — dấu phân cách phải là thứ tên
        # showroom không bao giờ mang.
        "VinFast Long Biên - Hà Nội",
        "VinFast Q.7, TP. Hồ Chí Minh",
    ],
)
def test_ma_nut_doc_lai_dung_nguyen_ven(showroom: str) -> None:
    choice = _doc(_cap(showroom))

    assert choice is not None
    assert choice.showroom == showroom
    assert choice.scheduled_at == WHEN


def test_giu_nguyen_mui_gio() -> None:
    """Mất múi giờ là lệch bảy tiếng trên một hệ lưu `TIMESTAMPTZ`, và lệch đó chỉ
    lộ ra khi khách tới showroom."""

    choice = _doc(_cap("VinFast Mỹ Đình"))

    assert choice is not None
    assert choice.scheduled_at.tzinfo is not None
    assert choice.scheduled_at.utcoffset() == WHEN.utcoffset()


@pytest.mark.parametrize(
    "message",
    [
        "chiều mai 3h",
        "",
        "__lichlaithu__",
        "__lichlaithu__|khong-phai-ngay|VinFast",
        "tôi chọn VF 8",
        # Mã của bản CŨ: ba mảnh, nhưng mảnh cuối là TÊN showroom có dấu, không
        # phải chữ ký. `hmac.compare_digest` NÉM `TypeError` khi so chuỗi có ký
        # tự ngoài ASCII — lượt prod LP21 chết ở đúng dòng đó, `act` nổ và khách
        # nhận câu an toàn "anh/chị đang tìm ô tô điện hay xe máy điện ạ?".
        "__lichlaithu__|2026-08-29T10:00:00+07:00|VinFast E-Car Hưng Yên",
    ],
)
def test_khong_phai_ma_nut_thi_khong_dat_lich(message: str) -> None:
    """Không cố sửa mã hỏng: mã sai định dạng nghĩa là client cũ hoặc ai đó gõ
    tay, và đặt lịch từ dữ liệu đoán được là kiểu sai tệ nhất ở bước này.

    Từ chối phải là `None`, KHÔNG BAO GIỜ là một ngoại lệ: mọi người gọi đều đọc
    hàm này như một phép kiểm tra, không ai bọc `try`."""

    assert _doc(message) is None


# ── Đồng ý / từ chối lái thử ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "message", ["có", "đồng ý", "ok", "được", "muốn", "dạ có ạ", "đăng ký đi", "vâng ạ", "vâng"]
)
def test_khach_nhan_loi(message: str) -> None:
    assert wants_test_drive(message) is True


@pytest.mark.parametrize("message", ["không", "thôi", "không cần", "để sau", "chưa cần", "thôi ạ"])
def test_khach_tu_choi(message: str) -> None:
    assert wants_test_drive(message) is False


@pytest.mark.parametrize("message", ["để xem", "chiều mai", "giá bao nhiêu", "", "   "])
def test_chua_ro_thi_khong_doan(message: str) -> None:
    """Đoán hộ ở đây là đặt lịch cho người chưa nhận lời, hoặc bỏ qua người vừa
    đồng ý. Ba kết quả chứ không hai."""

    assert wants_test_drive(message) is None
