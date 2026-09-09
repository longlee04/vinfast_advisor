"""Xin giảm một SỐ TIỀN cụ thể vẫn là mặc cả.

Lỗ có sẵn, tìm ra khi viết lưới cho cửa lái thử (2026-08-28):

    r"giảm\\s+(giá|cho|được|thêm|nữa)"

đòi một TỪ theo sau, nên *"giảm 20 triệu"* — dạng mặc cả cụ thể nhất, và là dạng
tốn tiền thật nhất — không khớp mẫu nào. Chính docstring của bộ mẫu ghi nó "ưu
tiên bắt nhầm hơn bỏ sót"; ca này đang bỏ sót.
"""

from __future__ import annotations

import re

import pytest

from src.agents.domain.quote_risk import _NEGOTIATION_PATTERNS


def _is_negotiation(message: str) -> bool:
    return any(re.search(pattern, message) for pattern in _NEGOTIATION_PATTERNS)


@pytest.mark.parametrize(
    "message",
    [
        "giảm 20 triệu được không",
        "đăng ký lái thử và giảm 20 triệu",
        "bớt 5 triệu nhé",
        "giảm 10tr thì em chốt",
        "hạ 15 triệu được không anh",
    ],
)
def test_xin_giam_mot_so_tien_cu_the_la_mac_ca(message: str) -> None:
    assert _is_negotiation(message)


@pytest.mark.parametrize(
    "message",
    [
        "xe giảm xóc có tốt không",
        "tầm chạy giảm nhiều khi trời lạnh không",
        "giá 496 triệu đúng không",
    ],
)
def test_cau_khong_mac_ca_thi_khong_bi_bat_nham(message: str) -> None:
    """Nới mẫu KHÔNG được biến mọi câu có số thành một lần mặc cả."""

    assert not _is_negotiation(message)
