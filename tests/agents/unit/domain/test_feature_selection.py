"""Khách chọn TẤT CẢ tính năng vừa liệt kê.

**Bug thật Sếp báo 2026-08-26**: khách đáp `"có tất cả"` cho câu hỏi tính năng và
nhận về lời từ chối phạm vi. Vệt quyết định cho thấy **cả tám cờ đều `false`** —
`customer_declined` đúng là `false` (đây không phải từ chối), mà cũng không cờ
nào nhận ra "khách chọn hết".

Phải làm HAI việc: mở cửa phạm vi, VÀ gán đúng những mã bot vừa liệt kê. Mở cửa
mà không gán thì `feature_mentions` vẫn rỗng — khách nói "tất cả" cũng như chưa
nói gì, và lượt sau agent hỏi lại y câu vừa hỏi.
"""

from __future__ import annotations

import pytest

from src.agents.domain.feature_selection import (
    UNKNOWN_QUESTION,
    offered_feature_codes,
    wants_all_offered_features,
)

_QUESTION = """Với ô tô cho đi làm, anh/chị cần những tính năng nào trong số dưới đây ạ?
- **cảnh báo điểm mù**: Nhận biết phương tiện ở khu vực khó quan sát bên hông xe.
- **kết nối Bluetooth**: Ghép điện thoại với hệ thống trên xe để truyền âm thanh.
- **móc gắn ghế trẻ em ISOFIX**: Móc ISOFIX cố định ghế trẻ em vào khung ghế sau."""


@pytest.mark.parametrize(
    "message",
    [
        "có tất cả",
        "tất cả",
        "tất cả luôn",
        "cho tôi tất cả",
        "dạ cho anh tất cả",
        "lấy hết",
        "chọn hết",
        "muốn tất cả",
        "toàn bộ",
        "tất cả các tính năng",
        # Gõ không dấu là cách viết rất thường, không phải lỗi gõ.
        "co tat ca",
        "tat ca luon",
    ],
)
def test_nhan_ra_khach_chon_het(message: str) -> None:
    assert wants_all_offered_features(message)


@pytest.mark.parametrize(
    "message",
    [
        # Mỗi câu dưới đây mang một ý RIÊNG. Đọc thành "chọn hết tính năng" là gán
        # cho khách một lựa chọn họ chưa nêu — cùng chiều sai với bẫy `"k"` nuốt
        # "khoá chống trộm": ăn mất câu trả lời thật.
        "tất cả đều đắt quá",
        "cho tôi xem tất cả xe",
        "tất cả bao nhiêu tiền",
        "cho tôi tất cả thông tin xe",
        "xe nào có hết tính năng này",
        # "hết" một mình không nói gì về việc chọn.
        "hết tiền rồi",
        "hết pin",
        # Hai ý gần nhau nhưng KHÁC nhau, mỗi ý một đường xử lý.
        "không cần",
        "em chọn giúp anh đi",
    ],
)
def test_cau_mang_y_rieng_khong_bi_doc_thanh_chon_het(message: str) -> None:
    assert not wants_all_offered_features(message)


# ── Suy mã từ chính câu hỏi lượt trước ───────────────────────────────────────


def test_lay_dung_ma_bot_vua_liet_ke() -> None:
    """Suy từ văn bản câu hỏi thay vì thêm cột DB: câu hỏi lượt 2 in nguyên nhãn
    tiếng Việt của từng mã, và bảng cụm chữ đã biết đọc đúng những nhãn đó."""

    assert offered_feature_codes(_QUESTION) == frozenset(
        {"BLIND_SPOT_MONITOR", "BLUETOOTH", "ISOFIX_ANCHORS"}
    )


@pytest.mark.parametrize("question", [None, "", UNKNOWN_QUESTION])
def test_khong_biet_luot_truoc_hoi_gi_thi_khong_gan_ma_nao(question: str | None) -> None:
    """`UNKNOWN_QUESTION` nghĩa là ĐỌC HỎNG, không phải "bot đã hỏi tính năng".
    Gán bừa ở đây là cộng điểm cho những tính năng khách chưa từng chọn."""

    assert offered_feature_codes(question) == frozenset()


def test_cau_hoi_khong_ve_tinh_nang_thi_khong_gan_ma_nao() -> None:
    """Bot hỏi ngân sách chứ không hỏi tính năng — "tất cả" lúc đó không trỏ vào
    tính năng nào cả."""

    assert offered_feature_codes("Anh/chị dự tính khoảng bao nhiêu cho chiếc xe này ạ?") == frozenset()
