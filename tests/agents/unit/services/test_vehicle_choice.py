"""Khách CHỐT một mẫu xe → gửi bảng tổng quan, không phải tra cứu chung.

Sếp 2026-08-26: *"đề xuất xong, khách chọn xe sau đó phải được gửi thông tin
xe"*. Nút "Chọn mẫu này" gửi `"Tôi chọn <tên>"`, mà `classify_query_attribute`
không xếp câu đó vào `OVERVIEW` — nên nó rơi về nhánh tra cứu chung và khách nhận
ít thông tin hơn hẳn so với lúc tự hỏi "VF 8 thế nào".
"""

from __future__ import annotations

import pytest

from src.agents.services.vehicle_overview import is_vehicle_choice


@pytest.mark.parametrize(
    "message",
    [
        "Tôi chọn VF 8 All New",
        "chọn VF 3",
        "anh chọn con VF 8",
        "dạ em chọn chiếc VF 6",
        "lấy VF 5",
        "chốt VF 9",
        "mua VF 3",
        # Gõ không dấu là cách viết rất thường.
        "toi chon VF 8",
    ],
)
def test_nhan_ra_loi_chon_dut_khoat(message: str) -> None:
    assert is_vehicle_choice(message)


@pytest.mark.parametrize(
    "message",
    [
        # ĐANG cân nhắc — cần so sánh, không cần bảng thông số một chiếc.
        "nên chọn VF 3 hay VF 5",
        "chọn xe nào thì tốt",
        "so sánh VF 2 và VF 5",
        "cái nào tốt hơn",
        "VF 8 thế nào",
        # NHỜ chọn ≠ ĐÃ chọn. Gửi thẳng thông số một chiếc là tự quyết hộ khách.
        "tư vấn giúp tôi chọn xe",
        "chọn giúp anh đi",
        "em chọn hộ anh",
        "gợi ý giúp tôi",
        # Sở thích, không phải lời chốt.
        "tôi thích xe màu đỏ",
    ],
)
def test_cau_chua_chot_thi_khong_doc_thanh_da_chon(message: str) -> None:
    """Mẫu lỏng ở đây gán cho khách một quyết định họ chưa nêu, và hệ gửi bảng
    thông số của chiếc xe SAI — cùng chiều sai với bẫy `"k"` nuốt "khoá chống trộm"."""

    assert not is_vehicle_choice(message)
