"""Đọc câu trả lời cho "còn băn khoăn gì về mẫu này không".

Trong đúng một ngày 2026-08-26, BA lần luồng chết vì cùng hình dạng: bot đặt câu
hỏi MỞ, khách đáp ngắn, bộ phân loại phạm vi đọc câu đáp như tin nhắn lạc đề rồi
đóng lượt. Bộ đọc này ra đời CÙNG LÚC với câu hỏi, không phải sau khi nó vỡ.
"""

from __future__ import annotations

import pytest

from src.agents.domain.concern_reply import (
    ConcernReply,
    PostPitchDecision,
    classify_concern_reply,
    classify_post_pitch_decision,
)


@pytest.mark.parametrize(
    "message",
    [
        "không",
        "không còn gì",
        "không có gì đâu",
        "không thắc mắc gì",
        "không băn khoăn gì",
        "ổn rồi",
        "tốt rồi",
        "hài lòng rồi",
        "được rồi",
        "xong rồi",
        "ok",
        "dạ không ạ",
        # Gõ không dấu là cách viết rất thường.
        "khong con gi",
    ],
)
def test_khach_da_yen_tam(message: str) -> None:
    assert classify_concern_reply(message) is ConcernReply.NO_CONCERN


@pytest.mark.parametrize(
    "message",
    [
        "còn, tôi muốn hỏi về pin",
        "còn một chút băn khoăn",
        "tôi lo về pin",
        "giá hơi cao",
        "đắt quá",
        "pin dùng được bao lâu?",
        "cho hỏi bảo hành thế nào",
        "tôi chưa hiểu về sạc",
        # Câu vừa mở bằng "không" vừa NÊU nỗi lo. Xét mẫu "hết vướng" trước thì
        # nó ăn mất vế sau và luồng đẩy khách sang lái thử ngay lúc họ vừa nói ra
        # một điều đang cản họ.
        "không, tôi lo về pin",
    ],
)
def test_khach_con_vuong(message: str) -> None:
    assert classify_concern_reply(message) is ConcernReply.HAS_CONCERN


@pytest.mark.parametrize("message", ["ừm", "cũng được", "để xem", "à", "", "   "])
def test_cau_mo_ho_thi_khong_doan_ho_khach(message: str) -> None:
    """Ba kết quả, không phải hai. "cũng được" không nói lên khách đã yên tâm hay
    đang ngần ngại — ép về một đầu là đoán hộ họ. Mơ hồ thì hỏi lại."""

    assert classify_concern_reply(message) is ConcernReply.UNCLEAR


# ── Câu THẬT từ logs, format lại cho câu hỏi hai lối (Sếp 2026-08-26) ─────────
#
# Bốn lỗi dưới đây tìm ra bằng cách bắn chính những câu khách đã gõ trên prod vào
# bộ đọc mới. Không câu nào là giả định.


@pytest.mark.parametrize("cau", ["uh đặt đi", "đặt lịch giúp anh", "um được", "đăng ký giúp em"])
def test_loi_nhan_loi_khong_bi_doc_thanh_loi_than_gia(cau: str) -> None:
    """Bỏ dấu xong "ĐẶT lịch" và "ĐẮT" là cùng một chuỗi `dat`.

    Bản đầu chặn bằng danh sách ĐEN các từ đứng sau ("lich", "lai thu"…) và thủng
    ngay: "uh đặt đi" → `dat di` không nằm trong danh sách → đọc thành lời than
    giá → đẩy khách vừa ĐỒNG Ý sang tư vấn viên. Sai hẳn hướng, không phải sai
    một nửa.

    Danh sách đen không bao giờ đủ. Luật đúng là lookahead TRẮNG: "đắt" chỉ được
    nhận khi theo sau là từ mức độ hoặc hết câu.
    """

    assert classify_post_pitch_decision(cau) is PostPitchDecision.TEST_DRIVE


@pytest.mark.parametrize("cau", ["đắt quá", "xe này đắt", "đắt hơn dự tính", "giá hơi cao", "đắt lắm"])
def test_loi_than_gia_that_van_phai_vao_tu_van_vien(cau: str) -> None:
    """Chiều ÂM của test trên: siết "đắt" lại không được làm mất lời than giá."""

    assert classify_post_pitch_decision(cau) is PostPitchDecision.HAS_CONCERN


@pytest.mark.parametrize(
    "cau",
    ["xe này pin đi được bao xa", "còn xe nào khác không", "bảo hành thế nào", "sạc mất bao lâu"],
)
def test_cau_hoi_khong_dau_hoi_van_la_cau_hoi(cau: str) -> None:
    """Khách gõ liền không chấm câu — rất phổ biến trên log thật.

    Chỉ dựa vào `\\?` thì đúng những câu hỏi thật rơi vào vùng không đọc được, và
    agent hỏi lại chính người vừa đặt câu hỏi cho mình.
    """

    assert classify_post_pitch_decision(cau) is PostPitchDecision.HAS_CONCERN


@pytest.mark.parametrize("cau", ["không cần", "thôi không", "thôi để sau", "chưa cần đâu"])
def test_loi_tu_choi_ro_rang_khong_roi_vao_vung_khong_doc_duoc(cau: str) -> None:
    """"thôi không" mở bằng "thôi" rồi đóng bằng "không".

    Thiếu "khong" trong tập ĐUÔI thì lời từ chối rõ ràng trả `UNCLEAR` — khách bị
    hỏi lại đúng câu họ vừa từ chối.
    """

    assert classify_post_pitch_decision(cau) is PostPitchDecision.DECLINED
