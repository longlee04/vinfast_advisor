"""Bảng từ khoá phải đọc được câu gõ THIẾU DẤU — nhưng không được mù về dấu.

Bug quan sát trên hệ thống thật: khách gõ `"gia lan banh cua vf 5"` (chỉ thiếu
dấu, không sai chính tả) và nhận về **bảng thông số đầy đủ** kèm giá niêm yết
496 triệu — trong khi họ hỏi giá LĂN BÁNH, tức con số còn thiếu phí trước bạ,
biển số và bảo hiểm. Trả giá niêm yết cho câu hỏi giá lăn bánh không phải trả
lời thiếu, đó là trả lời SAI một con số nhỏ hơn thực tế hàng chục triệu.

Nguyên nhân: mọi bảng từ khoá trong hệ thống chỉ `casefold()` chứ không bỏ dấu,
nên `"lan banh"` không bao giờ khớp `"lăn bánh"`.

Nhưng bỏ dấu VÔ ĐIỀU KIỆN lại hỏng theo hướng khác, và nặng hơn: tiếng Việt có
những cặp từ chỉ khác nhau ở dấu mà đều rất thông dụng — `"chỗ"`/`"cho"`,
`"giá"`/`"gia"`. Nên quy tắc là **khách gõ có dấu thì tin dấu họ gõ**.
"""

from __future__ import annotations

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.pricing_intent import PricingIntent, classify_pricing_intent
from src.agents.domain.text_normalization import contains_keyword, has_diacritics
from src.agents.domain.vehicle_overview import VehicleAttribute, classify_query_attribute

# ── Quy tắc nền ───────────────────────────────────────────────────────────────


def test_a_message_without_diacritics_is_matched_on_the_stripped_form() -> None:
    assert contains_keyword("gia lan banh cua vf 5", "lăn bánh") is True


def test_a_message_with_diacritics_is_matched_strictly() -> None:
    """Đây là guard chống nhóm lỗi nguy hiểm hơn.

    `"chỗ"` (ghế ngồi) và `"cho"` (giới từ) trùng nhau khi bỏ dấu. Bỏ dấu vô điều
    kiện thì `"giá bao nhiêu cho gia đình tôi"` bị đọc thành câu hỏi số CHỖ ngồi.
    """

    assert contains_keyword("VF 5 giá bao nhiêu cho gia đình tôi", "bao nhiêu chỗ") is False
    assert contains_keyword("vf 8 có hợp với gia đình tôi không", "giá") is False


def test_the_stripped_path_matches_on_word_boundaries() -> None:
    """Bỏ dấu làm không gian từ hẹp lại nên chuỗi con nguy hiểm hơn hẳn."""

    assert contains_keyword("cho toi cac xe may dien", "ô tô") is False
    assert contains_keyword("giai doan nay", "giá") is False


def test_has_diacritics_detects_mixed_and_bare_text() -> None:
    assert has_diacritics("giá lăn bánh") is True
    assert has_diacritics("gia lan banh") is False
    assert has_diacritics("") is False


# ── A7-9: giá lăn bánh ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "message",
    ["gia lan banh cua vf 5", "giá lăn bánh của vf 5", "gia lan banh vf5", "vf5 ra bien het bao nhieu"],
)
def test_an_on_road_price_question_is_recognised_with_or_without_diacritics(
    message: str,
) -> None:
    """Ca người dùng báo lỗi."""

    assert classify_pricing_intent(message, build_canonical_text(message)) is PricingIntent.ON_ROAD_PRICE_LOOKUP


@pytest.mark.parametrize("message", ["chi phi nuoi xe vf5", "chi phí nuôi xe vf5"])
def test_a_tco_question_is_recognised_with_or_without_diacritics(message: str) -> None:
    assert classify_pricing_intent(message, build_canonical_text(message)) is PricingIntent.TCO_ESTIMATE_LOOKUP


@pytest.mark.parametrize("message", ["lai suat tra gop vf5", "lãi suất trả góp vf5"])
def test_custom_financing_is_recognised_with_or_without_diacritics(message: str) -> None:
    assert classify_pricing_intent(message, build_canonical_text(message)) is PricingIntent.CUSTOM_FINANCING


@pytest.mark.parametrize("message", ["vf5 gia bao nhieu", "vf5 giá bao nhiêu"])
def test_a_plain_list_price_question_is_not_an_on_road_question(message: str) -> None:
    """Giá niêm yết và giá lăn bánh là hai câu hỏi khác nhau, hai câu trả lời khác nhau."""

    assert classify_pricing_intent(message, build_canonical_text(message)) is PricingIntent.NONE


# ── Thuộc tính xe ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("vf5 gia bao nhieu", VehicleAttribute.PRICE),
        ("vf5 giá bao nhiêu", VehicleAttribute.PRICE),
        ("gia lan banh cua vf 5", VehicleAttribute.PRICE),
        ("vf5 mau gi", VehicleAttribute.COLOR),
        ("vf5 màu gì", VehicleAttribute.COLOR),
        ("vf5 co may cho ngoi", VehicleAttribute.SEAT_COUNT),
        ("vf5 có mấy chỗ ngồi", VehicleAttribute.SEAT_COUNT),
        ("vf5 di duoc bao nhieu km", VehicleAttribute.RANGE),
        ("vf5 chinh sach pin", VehicleAttribute.WARRANTY),
        ("vf5 tui khi", VehicleAttribute.AIRBAG),
        ("vf5 thong so", VehicleAttribute.SPECS),
    ],
)
def test_attribute_questions_survive_missing_diacritics(message: str, expected: VehicleAttribute) -> None:
    assert classify_query_attribute(message) is expected


def test_a_family_compound_is_not_read_as_a_price_question() -> None:
    """`"gia đình"` chứa `"gia"`; bỏ dấu vô điều kiện sẽ đọc thành câu hỏi GIÁ,
    và khách nhận đúng một dòng giá thay vì bảng đầy đủ họ đang cần."""

    assert classify_query_attribute("vf 8 có hợp với gia đình tôi không") is (VehicleAttribute.UNKNOWN)


def test_a_real_price_question_still_wins_over_a_nearby_compound() -> None:
    assert classify_query_attribute("VF 5 giá bao nhiêu cho gia đình tôi") is (VehicleAttribute.PRICE)
