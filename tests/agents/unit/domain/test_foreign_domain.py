"""Chủ đề rõ ràng KHÔNG phải xe — bản đọc tất định, hẹp và có chủ đích.

Bối cảnh 2026-08-26: `"tư vấn cho tôi mua cổ phiếu nào"` được bộ phân loại gắn
`IN_SCOPE` **5/5 lần**, dù prompt đã có nguyên văn ví dụ đó là `OUT_OF_SCOPE` và
đã kiểm bản prompt mới thật sự sống trong container. Lever prompt hết tác dụng.

**Đây KHÔNG phải giải pháp tổng quát** và không cố làm thế: chủ đề ngoài ngành là
tập vô hạn, chạy theo nó bằng danh sách là cuộc đua không thắng được. Nó chỉ đóng
đúng vài lĩnh vực hay bị hỏi nhầm, nơi từ khoá **không bao giờ** xuất hiện trong
một câu tư vấn xe thật.

Nên test âm tính ở đây quan trọng hơn test dương tính.
"""

from __future__ import annotations

import pytest

from src.agents.domain.foreign_domain import names_a_foreign_domain


@pytest.mark.parametrize(
    "message",
    [
        "tư vấn cho tôi mua cổ phiếu nào",
        "tư vấn giúp tôi cách nấu phở",
        "anh muốn mua nhà đất ở đâu",
        "tư vấn bảo hiểm nhân thọ giúp em",
        "cho hỏi chứng khoán hôm nay",
    ],
)
def test_clearly_other_fields_are_recognised(message: str) -> None:
    assert names_a_foreign_domain(message) is True


@pytest.mark.parametrize(
    "message",
    [
        # Câu tư vấn xe thật — không câu nào được dính.
        "anh muốn tư vấn",
        "tôi cần tư vấn",
        "tư vấn giúp em với",
        "VF 5 giá bao nhiêu",
        "khoảng 500 triệu",
        "khoá chống trộm",
        "anh hay chở hàng nặng",
        "xe nào chạy được xa nhất",
        "cho tôi gặp tư vấn viên",
        # "bảo hành" KHÁC "bảo hiểm" — một chữ khác nhau, một bên là dịch vụ xe.
        "chính sách bảo hành thế nào",
        # "nhà" đứng riêng là chuyện sạc tại nhà, không phải nhà đất.
        "nhà anh có ổ cắm ở chỗ để xe",
    ],
)
def test_real_car_advisory_sentences_are_never_flagged(message: str) -> None:
    assert names_a_foreign_domain(message) is False
