"""Đọc quãng đường MỖI NGÀY từ lời khách, ở bất kỳ lượt nào.

Đây là lời hứa "sửa được tại chỗ" của bảng chi phí: khách nói một con số mới thì
lượt đó tính lại ngay, không lùi chặng, không hỏi lại câu nào. Không có bộ đọc
này thì hai cái nút mời sửa dưới bảng chỉ là chữ.
"""

from __future__ import annotations

import pytest

from src.agents.domain.range_normalizer import daily_distance_from_message

# ── Khách SỬA quãng đường ở bất kỳ lượt nào (Sếp 2026-08-26) ─────────────────


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ngày em đi 80km, em đăng ký ở Hà Nội", 80),
        ("mỗi ngày 30km", 30),
        ("1 ngày đi 45 km", 45),
        ("đi làm khoảng 30 km mỗi ngày", 30),
        ("em chạy 25km/ngày", 25),
    ],
)
def test_doc_duoc_quang_duong_moi_ngay(message: str, expected: int) -> None:
    """Chạy thật trên prod: sau khi khách chọn xe, phiên ở chặng quyết định và
    không còn slot nào "đang chờ", nên `_salvaged_slots` không chạy cho quãng
    đường.

    Khách gõ "ngày em đi 80km" mà `required_range_km` giữ nguyên 30 của lượt
    trước — bảng chi phí vẫn tính theo con số cũ. Mẫu bằng chứng cũ đòi đúng cụm
    "mỗi ngày" nên không khớp "ngày em đi".
    """

    assert daily_distance_from_message(message) == expected


@pytest.mark.parametrize(
    "message",
    ["tầm chạy 400 km", "xe này đi được 500km một lần sạc", "VF 8", "không có số nào", "5 chỗ"],
)
def test_so_km_khong_kem_chu_ngay_thi_khong_phai_nhu_cau(message: str) -> None:
    """Một con số km trơ là TẦM HOẠT ĐỘNG của xe, không phải nhu cầu của khách.

    Thiếu vế "ngày" thì chính bảng thông số xe tự ghi đè nhu cầu khách.
    """

    assert daily_distance_from_message(message) is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("mỗi ngày anh đi 40km", 40),
        ("ngày em đi 80km, em đăng ký ở Hà Nội", 80),
        ("anh chạy 60 km/ngày", 60),
        ("một ngày tầm 25km thôi", 25),
    ],
)
def test_stated_daily_distance_updates_the_assumption(message: str, expected: int) -> None:
    assert daily_distance_from_message(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "thi thoảng có ngày anh chạy 150km",
        "thỉnh thoảng ngày nào rảnh đi 200km",
        "cuối tuần đi 180 km mỗi ngày",
        "đôi khi một ngày 120km",
        "ít khi đi, có ngày 90km",
    ],
)
def test_occasional_distance_leaves_the_assumption_alone(message: str) -> None:
    """Sếp 2026-08-27: nói "thi thoảng" thì KHÔNG được tính thành nhu cầu mỗi ngày."""

    assert daily_distance_from_message(message) is None
