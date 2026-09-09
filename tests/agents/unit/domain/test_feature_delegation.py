"""Khách NHỜ agent chọn hộ ≠ khách TỪ CHỐI trả lời.

`slot_salvage.is_non_answer` gộp hai thứ đó làm một: `"tư vấn giúp"` và
`"tùy em"` nằm chung nhóm với `"chưa biết"`. Ở lượt hỏi ngân sách thì gộp như vậy
đúng — không câu nào trong đó rút ra được một con số. Ở lượt hỏi TÍNH NĂNG thì
sai: khách vừa giao việc chọn cho agent, mà hệ đóng ô lại rồi đi tiếp.

Vị từ này tách riêng đúng phần "giao việc", và nó được hỏi TRƯỚC `is_non_answer`.
`is_non_answer` giữ nguyên — bốn chỗ đang dùng nó với bốn sắc thái khác nhau.
"""

from __future__ import annotations

import pytest

from src.agents.domain.feature_delegation import delegates_choice_to_agent


@pytest.mark.parametrize(
    "customer_words",
    [
        "em chọn giúp anh",
        "em chọn hộ anh với",
        "anh hay đi làm trong phố, em chọn tính năng giúp anh nhé",
        "nhờ em tư vấn giúp",
        "tùy em",
        "tuỳ em thôi",
        "em gợi ý giúp anh",
        "anh không rành, em chọn giúp",
        "em quyết định giúp anh",
        "em thấy cái nào hợp thì chọn giúp anh",
        # Dạng "nhờ" — không có chữ "giúp"/"hộ" nào ở sau động từ.
        "nhờ em chọn",
        "nhờ em chọn tính năng",
        "anh nhờ em tư vấn",
    ],
)
def test_khach_giao_viec_chon_cho_agent(customer_words: str) -> None:
    assert delegates_choice_to_agent(customer_words) is True


@pytest.mark.parametrize(
    "customer_words",
    [
        # Bẫy chữ "k" của mục 3.5: một tính năng thật, không được nuốt.
        "khoá chống trộm",
        "khoá chống trộm với sạc nhanh",
        # Từ chối thuần — `is_non_answer` vẫn lo, không phải giao việc.
        "không cần tính năng gì",
        "thôi khỏi",
        # Xin gặp NGƯỜI. Chạm chữ "tư vấn" nhưng là nhánh HITL, không phải giao việc.
        "cho tôi gặp tư vấn viên",
        "anh muốn gặp tư vấn viên hỗ trợ",
        # Mở luồng tư vấn — `advisory_restart` lo, không phải giao việc.
        "anh muốn tư vấn",
        "tôi muốn tư vấn xe",
        # Khách TỰ chọn, không nhờ ai.
        "anh chọn pin tháo rời",
        "cho anh xem xe có khoá chống trộm",
        # Câu trả lời slot bình thường.
        "khoảng 500 triệu",
        "nhà anh có ổ cắm",
        # "nhờ" đứng một mình, không giao việc chọn cho ai.
        "nhờ anh báo giá giúp",
    ],
)
def test_khong_bat_nham_cau_khac(customer_words: str) -> None:
    assert delegates_choice_to_agent(customer_words) is False


def test_cau_rong_khong_phai_giao_viec() -> None:
    assert delegates_choice_to_agent("") is False
    assert delegates_choice_to_agent("   ") is False
