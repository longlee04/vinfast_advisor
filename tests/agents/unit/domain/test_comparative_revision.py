"""Khách xin đổi đề xuất bằng lối SO SÁNH — phải đọc tất định, không đoán.

BUG PROD 2026-08-26. Cùng một câu *"nếu anh muốn 1 chiếc nhỏ hơn thì sao"* xuất
hiện ở hai phiên; `payload->llm` của cả hai đều là `intents: []`, `slots_gained:
{}` — mô hình không hiểu gì — nhưng nhãn phạm vi nó bịa ra thì khác nhau:

- `705dd9ca`: OUT_OF_SCOPE → *"câu này nằm ngoài phần em phụ trách"*, lượt chết;
- `1e9ec5c3`: IN_SCOPE → đề xuất lại **VF 8**, đúng chiếc khách vừa chê là to.

Bài kiểm chia đúng hai tầng của module: KHUNG (có `hơn` là có lời xin đổi — không
bao giờ để lượt chết) và THUỘC TÍNH (tra bằng bảng từ vựng đã có sẵn).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.comparative_revision import (
    SEEN_LOWEST_PRICE_KEY,
    budget_ceiling_below_seen,
    detect_comparative_revision,
)

# ── Tầng KHUNG ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "user_message",
    [
        "nếu anh muốn 1 chiếc nhỏ hơn thì sao",
        "có mẫu nào rẻ hơn không em",
        "anh cần cốp rộng hơn",
        "xe gầm cao hơn được không",
        # Không quy về mã nào — nhưng VẪN là lời xin đổi. Đây là điều quan trọng
        # nhất của tầng khung: lượt không chết chỉ vì ta chưa hiểu "hơn ở chỗ nào".
        "đi lại tiện lợi hơn",
        "xe nào bền hơn ạ",
    ],
)
def test_the_frame_alone_is_enough_to_recognise_a_revision(user_message: str) -> None:
    assert detect_comparative_revision(build_canonical_text(user_message)) is not None


@pytest.mark.parametrize(
    "user_message",
    [
        # Lượt KHAI NHU CẦU, không phải lượt đổi kết quả. Thiếu ràng buộc "hơn"
        # thì những câu này bị đọc thành lệnh đổi đề xuất và cuộc tư vấn nhảy cóc
        # qua bước khách còn chưa nói xong.
        "anh cần 1 chiếc nhỏ gọn thôi",
        "tôi cần xe rộng rãi cho gia đình",
        "anh có 500 triệu và muốn xe nhỏ gọn đi trong nội thành",
        "em ưu tiên xe tiết kiệm, dễ đi trong phố",
        "giá hơi cao",
        "cho anh lái thử",
    ],
)
def test_a_plain_need_statement_has_no_comparative_frame(user_message: str) -> None:
    assert detect_comparative_revision(build_canonical_text(user_message)) is None


def test_a_named_model_comparison_is_not_a_revision_request() -> None:
    """ "VF 8 rộng hơn VF 7 không ạ" là câu hỏi SO SÁNH, không phải xin đổi đề xuất.

    Đọc nhầm chiều này sẽ thay một bảng so sánh khách hỏi bằng một danh sách
    khách không hỏi.
    """

    canonical = build_canonical_text("VF 8 rộng hơn VF 7 không ạ")

    assert detect_comparative_revision(canonical, vehicle_mentions=True) is None


# ── Tầng THUỘC TÍNH ──────────────────────────────────────────────────────────


def test_an_existing_trait_phrase_needs_no_new_code() -> None:
    """ "cốp rộng hơn" chạy nhờ `perceptual_traits._TRAIT_CUES`, không nhờ dòng nào viết riêng."""

    revision = detect_comparative_revision(build_canonical_text("anh cần cốp rộng hơn"))

    assert revision is not None
    assert revision.trait_codes == ("TRAIT_LARGE_CARGO",)


def test_a_compound_phrase_beats_the_bare_adjective_bridge() -> None:
    """ "cốp rộng" là cụm cụ thể — không được kéo thêm `7_SEATER` từ chữ "rộng".

    Để cầu nối chạy chồng lên sẽ biến một câu về cốp xe thành một câu đòi thêm
    hàng ghế.
    """

    revision = detect_comparative_revision(build_canonical_text("anh cần cốp rộng hơn"))

    assert revision is not None
    assert revision.feature_codes == ()


def test_an_existing_feature_phrase_needs_no_new_code() -> None:
    """ "cửa sổ trời" đã nằm trong `claim_policy._FEATURE_CLAIM_CUES`."""

    revision = detect_comparative_revision(build_canonical_text("có mẫu nào cửa sổ trời rộng hơn không"))

    assert revision is not None
    assert "PANORAMIC_ROOF" in revision.feature_codes


@pytest.mark.parametrize(
    "user_message, expected_code",
    [
        ("nếu anh muốn 1 chiếc nhỏ hơn thì sao", "COMPACT_SIZE"),
        ("anh cần xe to hơn", "7_SEATER"),
        ("xe nào đi xa hơn", "HIGH_RANGE_BATTERY"),
        ("cho anh xe cao cấp hơn", "PANORAMIC_ROOF"),
    ],
)
def test_a_bare_adjective_maps_to_a_scoring_code(user_message: str, expected_code: str) -> None:
    revision = detect_comparative_revision(build_canonical_text(user_message))

    assert revision is not None
    assert expected_code in revision.feature_codes


def test_a_price_request_carries_no_feature_code() -> None:
    """Rẻ hơn là chuyện của GIÁ.

    Gán một mã trang bị ở đây là đặt vào miệng khách một yêu cầu họ không nêu;
    trần ngân sách cứng (Sếp 2026-08-26) đã chặn phía trên rồi.
    """

    revision = detect_comparative_revision(build_canonical_text("có mẫu nào rẻ hơn không em"))

    assert revision is not None
    assert revision.cheaper is True
    assert revision.feature_codes == ()


def test_an_unmapped_attribute_is_still_a_valid_revision() -> None:
    """Không hiểu "hơn ở chỗ nào" thì vẫn phải đổi kết quả, chỉ là không có hướng."""

    revision = detect_comparative_revision(build_canonical_text("đi lại tiện lợi hơn"))

    assert revision is not None
    assert revision.attribute_known is False
    assert revision.feature_codes == ()


def test_only_the_words_before_the_comparative_are_read() -> None:
    """Cửa sổ giữ đúng quan hệ "thuộc tính NÀO hơn".

    Tra cả câu sẽ nhặt luôn "cốp rộng" — thứ khách vừa nói là ĐÃ CÓ, không phải
    thứ họ đang tìm.
    """

    revision = detect_comparative_revision(build_canonical_text("anh có xe cốp rộng rồi, giờ muốn một chiếc rẻ hơn"))

    assert revision is not None
    assert revision.cheaper is True
    assert revision.trait_codes == ()


def test_a_child_seat_question_is_not_a_price_request() -> None:
    """Ca ÂM TÍNH của khớp chuỗi con: "re" nằm trong "trẻ em"."""

    revision = detect_comparative_revision(build_canonical_text("xe nào có ghế trẻ em an toàn hơn"))

    assert revision is not None
    assert revision.cheaper is False


# ── Trần ngân sách cho lượt "rẻ hơn" ─────────────────────────────────────────


def test_the_new_ceiling_sits_just_under_the_cheapest_car_seen() -> None:
    """Ngay dưới MỘT ĐỒNG, không phải một tỉ lệ phần trăm nào.

    Mọi con số kiểu "hạ 10%" đều là số bịa; "dưới chiếc rẻ nhất khách vừa xem"
    là đúng nghĩa đen của điều khách vừa nói. Trần cứng (Sếp 2026-08-26) làm nốt
    phần còn lại — chiếc vừa bị chê đắt rơi ra theo đúng luật đang chạy.
    """

    ceiling = budget_ceiling_below_seen({SEEN_LOWEST_PRICE_KEY: "646000000"})

    assert ceiling == Decimal("645999999")


def test_no_delivered_price_means_no_new_ceiling() -> None:
    """Chưa từng đưa thẻ xe nào thì không có gì để so — giữ nguyên hồ sơ."""

    assert budget_ceiling_below_seen(None) is None
    assert budget_ceiling_below_seen({}) is None
    assert budget_ceiling_below_seen({"stage": "AWAITING_CHOICE"}) is None


def test_a_broken_price_does_not_raise() -> None:
    """Dữ liệu hỏng không được phép làm chết lượt của khách."""

    assert budget_ceiling_below_seen({SEEN_LOWEST_PRICE_KEY: "gia-hong"}) is None
