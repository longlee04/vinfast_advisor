"""Đọc lời CHỌN một mẫu xe ở chặng sau đề xuất.

Chặng đó chỉ có đúng một việc phải làm: nhận ra khách vừa chỉ vào chiếc nào.
Đọc sót thì luồng đứng im dù khách đã trả lời; đọc thừa thì hệ gửi bảng thông số
của chiếc xe SAI — bài học `"k"` nuốt `"khoá chống trộm"`.
"""

from __future__ import annotations

import pytest

from src.agents.services.vehicle_overview import is_bare_vehicle_choice

# ── Tên xe TRƠ TRỌI ở chặng chờ khách chọn mẫu (Sếp 2026-08-26) ──────────────


@pytest.mark.parametrize(
    "message,name",
    [("VF 8", "VF 8"), ("VF 8 ạ", "VF 8"), ("con VF 8 nhé", "VF 8"), ("mẫu VF 6 đi", "VF 6")],
)
def test_ten_xe_tro_troi_la_loi_chon(message: str, name: str) -> None:
    """Đo trên câu thật: khách gõ đúng "VF 8" sau khi xem ba thẻ đề xuất.

    `is_vehicle_choice` đòi một ĐỘNG TỪ nên câu đó trả `False`, và cả luồng đứng
    lại ở chặng chờ chọn — khách đã chỉ vào chiếc xe mà hệ không nhận.
    """

    assert is_bare_vehicle_choice(message, name) is True


@pytest.mark.parametrize(
    "message,name",
    [
        ("VF 8 giá bao nhiêu", "VF 8"),
        ("VF 8 có bản nào rẻ hơn", "VF 8"),
        ("VF 8 với VF 9 khác gì nhau", "VF 8"),
        ("cho anh xem VF 3", "VF 3"),
    ],
)
def test_ten_xe_kem_cau_hoi_khong_phai_loi_chon(message: str, name: str) -> None:
    """Chiều ÂM — và là lý do vị từ này KHÔNG nới `is_vehicle_choice`.

    Nới ở đó thì mọi lượt nhắc tên xe trong toàn hệ thống thành lời chọn, kể cả
    khách đang hỏi giá. Tập từ đệm phải ĐÓNG, cùng khuôn các bộ đọc đuôi khác.
    """

    assert is_bare_vehicle_choice(message, name) is False
