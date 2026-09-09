"""[A7-5] Phân loại lượt: yêu cầu mới, hay chỉ là một tiếng "ok".

Hướng nguy hiểm của module này là phân loại NHẦM sang `ACKNOWLEDGMENT`: khi đó
lượt bị đáp bằng câu dẫn bước tiếp theo và thông tin/yêu cầu khách vừa nói bị
nuốt mất. Nhầm chiều ngược lại chỉ tốn một lần đánh giá thừa.
"""

from __future__ import annotations

import pytest

from src.agents.domain.turn_classification import TurnType, classify_turn

FORM = {"vehicle_type": "CAR", "passenger_count": 5}


def _classify(message: str, before: dict | None = None, after: dict | None = None) -> TurnType:
    return classify_turn(
        form_before=FORM if before is None else before,
        form_after=FORM if after is None else after,
        user_message=message,
    )


@pytest.mark.parametrize(
    "message",
    [
        "ok xe có vẻ được đấy",
        "ok",
        "oke",
        "được rồi",
        "nghe ổn",
        "vậy đi",
        "chốt",
        "đồng ý",
        "cảm ơn em",
    ],
)
def test_confirmation_without_new_information_is_an_acknowledgment(message: str) -> None:
    assert _classify(message) is TurnType.ACKNOWLEDGMENT


def test_a_short_turn_outside_the_whitelist_is_still_an_acknowledgment() -> None:
    """Whitelist không bao giờ đủ; câu rất ngắn mà không lấp được slot nào cũng
    không mang yêu cầu gì để đánh giá lại."""

    assert _classify("uhm") is TurnType.ACKNOWLEDGMENT


def test_new_information_beats_the_acknowledgment_wording() -> None:
    """`has_new_info` xét TRƯỚC mọi thứ khác.

    "ok, 7 chỗ nhé" vừa có từ xác nhận vừa lấp một slot. Đọc nó thành xác nhận
    là nuốt mất đúng thông tin khách vừa cho.
    """

    turn = _classify(
        "ok 7 chỗ nhé",
        before={"vehicle_type": "CAR"},
        after={"vehicle_type": "CAR", "passenger_count": 7},
    )

    assert turn is TurnType.NEW_REQUEST


def test_a_follow_up_question_is_a_new_request() -> None:
    assert _classify("có màu đỏ không") is TurnType.NEW_REQUEST


def test_a_short_question_is_not_an_acknowledgment() -> None:
    """ "giá sao" chỉ 7 ký tự nhưng là một yêu cầu thật.

    Nếu chỉ xét độ dài, câu này rơi vào nhánh xác nhận và khách hỏi giá lại được
    mời đi lái thử.
    """

    assert _classify("giá sao") is TurnType.NEW_REQUEST
    assert _classify("thế nào") is TurnType.NEW_REQUEST
    assert _classify("bao nhiêu") is TurnType.NEW_REQUEST


def test_a_long_neutral_sentence_defaults_to_new_request() -> None:
    """Không chắc thì đánh giá lại đầy đủ — mặc định an toàn."""

    assert _classify("em đang phân vân giữa hai mẫu xe này") is TurnType.NEW_REQUEST


def test_an_empty_turn_is_not_an_acknowledgment() -> None:
    assert _classify("   ") is TurnType.NEW_REQUEST


def test_missing_form_snapshots_are_treated_as_unchanged() -> None:
    """State cũ (hoặc gọi graph trực tiếp) không có ảnh chụp form đầu lượt."""

    assert classify_turn(form_before=None, form_after=None, user_message="ok") is TurnType.ACKNOWLEDGMENT


def test_an_acknowledgment_survives_slots_the_extractor_invented() -> None:
    """Đo được trên hệ thống thật: bước trích slot ghi ra thứ khách chưa nói.

    "ok xe có vẻ được đấy" làm nó ghi `vehicle_type=CAR` (vì có chữ "xe"), còn
    "được đấy" làm nó ghi thẳng `passenger_count=5` — trong câu không có con số
    nào. Tin vào delta form thì đúng hai câu xác nhận điển hình nhất bị đọc thành
    yêu cầu mới, và bug ban đầu còn nguyên.
    """

    invented_type = _classify("ok xe có vẻ được đấy", before={}, after={"vehicle_type": "CAR"})
    invented_count = _classify(
        "được đấy",
        before={"vehicle_type": "CAR"},
        after={"vehicle_type": "CAR", "passenger_count": 5},
    )

    assert invented_type is TurnType.ACKNOWLEDGMENT
    assert invented_count is TurnType.ACKNOWLEDGMENT


def test_a_request_verb_next_to_an_ack_word_is_still_a_request() -> None:
    """ "ok" đứng cạnh một nhu cầu thật thì nhu cầu thắng."""

    assert _classify("ok em muốn xe chở được nhiều đồ") is TurnType.NEW_REQUEST
    assert _classify("ok cho em xem thêm bản cao hơn") is TurnType.NEW_REQUEST


def test_digits_beat_the_ack_whitelist() -> None:
    """Chữ số đọc thẳng từ lời khách, không bị bước trích slot làm nhiễu."""

    assert _classify("ok 7 chỗ nhé", before={}, after={}) is TurnType.NEW_REQUEST
    assert _classify("được đấy, 800 triệu") is TurnType.NEW_REQUEST


def test_a_genuinely_new_short_answer_still_counts_as_a_request() -> None:
    """Không có từ xác nhận nào thì delta form vẫn là bằng chứng chính."""

    turn = _classify("xe máy điện", before={}, after={"vehicle_type": "ELECTRIC_MOTORBIKE"})

    assert turn is TurnType.NEW_REQUEST
