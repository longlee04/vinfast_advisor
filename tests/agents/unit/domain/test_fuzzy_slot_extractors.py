"""Điểm nối THỨ HAI của tầng nhận diện: bộ trích slot dự phòng cho A7-10.

Cắm bốn lớp vào graph là chưa đủ để giữ lời hứa "ưu tiên diễn giải theo slot
đang chờ": `chain._resume_pending_slot` chạy TRƯỚC `graph.ainvoke` và kết thúc
lượt ngay khi giải được, nên node `recognize_intent` không bao giờ nhìn thấy một
lượt đang trả lời câu hỏi slot.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.fuzzy_slot_extractors import (
    FUZZY_FALLBACK_EXTRACTORS,
    fuzzy_detect_province,
)
from src.agents.domain.pricing_intent import detect_province
from src.agents.services.pending_slot import PendingSlotServiceImpl, pending_for_province

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)


def _pending() -> dict:
    return pending_for_province("vf5-id", "VF 5", NOW).to_payload()


def _service() -> PendingSlotServiceImpl:
    return PendingSlotServiceImpl(fallback_extractors=FUZZY_FALLBACK_EXTRACTORS)


# ── Bộ khớp mờ cho tỉnh/thành ─────────────────────────────────────────────────


def test_a_correctly_written_province_still_resolves() -> None:
    assert fuzzy_detect_province("hà nội") == "HN"
    assert fuzzy_detect_province("tôi ở Đà Nẵng") == "DN"


def test_a_province_typed_with_a_wrong_tone_mark_now_resolves() -> None:
    """Bộ chính khớp CHÍNH XÁC nên chỉ chấp nhận đúng hai cách viết đã liệt kê
    ("hà nội" có dấu đầy đủ, hoặc "ha noi" không dấu hoàn toàn).

    Gõ nhầm MỘT dấu — thứ xảy ra liên tục trên bàn phím điện thoại — rơi vào
    khoảng giữa và trước đây bị bỏ hẳn.
    """

    assert detect_province("hà nôi", build_canonical_text("hà nôi")) is None
    assert fuzzy_detect_province("hà nôi") == "HN"


def test_a_wrong_letter_is_deliberately_left_unresolved() -> None:
    """Đoán sai tỉnh nghĩa là báo sai phí trước bạ hàng chục triệu đồng.

    "ha nol" chỉ đạt 83 điểm, dưới ngưỡng riêng 88 của bộ trích slot (cao hơn
    ngưỡng chung của Lớp 2). Hỏi lại là câu trả lời đúng ở đây, không phải đoán.
    """

    assert fuzzy_detect_province("ha nol") is None


def test_a_two_letter_code_only_matches_exactly() -> None:
    """ "hn"/"ct"/"kh" là mã hai ký tự — nới lỏng thì mọi từ hai chữ cái trong
    câu đều có thể biến thành một tỉnh."""

    assert fuzzy_detect_province("hn") == "HN"
    assert fuzzy_detect_province("hm") is None


def test_an_unrelated_message_resolves_to_nothing() -> None:
    assert fuzzy_detect_province("cho tôi xem bảng giá") is None
    assert fuzzy_detect_province("") is None


# ── Thứ tự bộ chính → bộ dự phòng ─────────────────────────────────────────────


def test_the_exact_matcher_runs_first_and_its_accuracy_is_unchanged() -> None:
    """Đảo thứ tự thì một câu khách viết đúng vẫn có thể bị bộ mờ đọc lệch."""

    resolution = _service().resolve(payload=_pending(), user_message="hà nội", canonical=build_canonical_text("hà nội"), now=NOW)

    assert resolution.handled is True
    assert resolution.filled_form is not None
    assert resolution.filled_form["province"] == "HN"


def test_the_fallback_rescues_a_turn_the_exact_matcher_would_have_dropped() -> None:
    resolution = _service().resolve(payload=_pending(), user_message="hà nôi", canonical=build_canonical_text("hà nôi"), now=NOW)

    assert resolution.handled is True
    assert resolution.filled_form is not None
    assert resolution.filled_form["province"] == "HN"


def test_without_the_fallback_the_old_behaviour_is_preserved() -> None:
    """Bộ dự phòng là tuỳ chọn: không nối thì A7-10 chạy y như trước."""

    resolution = PendingSlotServiceImpl().resolve(payload=_pending(), user_message="hà nôi", canonical=build_canonical_text("hà nôi"), now=NOW)

    assert resolution.filled_form is None
    assert resolution.reply is not None  # hỏi lại như cũ


def test_a_genuinely_unrelated_answer_still_falls_through() -> None:
    """Bộ dự phòng không được biến mọi câu thành một tỉnh."""

    resolution = _service().resolve(payload=_pending(), user_message="thôi tôi xem xe khác", canonical=build_canonical_text("thôi tôi xem xe khác"), now=NOW)

    assert resolution.filled_form is None


def test_the_fallback_table_only_covers_slots_that_can_be_pending() -> None:
    """`DEFAULT_EXTRACTORS` của A7-10 cũng chỉ có `province`."""

    assert set(FUZZY_FALLBACK_EXTRACTORS) == {"province"}
