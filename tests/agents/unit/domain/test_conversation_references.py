import pytest

from src.agents.domain.conversation_references import refers_to_current_vehicle, resolve_vehicle_references


def test_resolves_remaining_model_after_one_was_eliminated() -> None:
    assert resolve_vehicle_references(
        user_message="Mẫu còn lại giá bao nhiêu?",
        conversation_context="Đã loại VF 5 vì chật; mẫu đang tiếp tục là VF 7.",
        raw_mentions=["VF 5", "VF 7"],
    ) == ["VF 7"]


def test_resolves_second_model_using_order_in_recent_transcript() -> None:
    assert resolve_vehicle_references(
        user_message="Mẫu thứ hai đi được bao xa?",
        conversation_context="USER: So sánh VF 5 và VF 7 giúp tôi.",
        raw_mentions=[],
    ) == ["VF 7"]


def test_resolves_model_customer_just_eliminated_even_when_llm_returns_other_model() -> None:
    assert resolve_vehicle_references(
        user_message="Không, tôi đổi ý, xem lại mẫu tôi vừa loại.",
        conversation_context="Khách đã loại VF 5 vì chật và đang xem VF 7.",
        raw_mentions=["VF 7"],
    ) == ["VF 5"]


def test_does_not_import_a_model_without_a_reference_cue() -> None:
    assert (
        resolve_vehicle_references(
            user_message="Tôi muốn xem xe khoảng 500 triệu.",
            conversation_context="Phiên trước có nhắc VF 7.",
            raw_mentions=["VF 7"],
        )
        == []
    )


@pytest.mark.parametrize(
    "message",
    ["xe này sạc đầy mất bao lâu", "chiếc này có bao nhiêu màu", "mẫu đó chạy được bao xa", "con này giá bao nhiêu"],
)
def test_pronoun_points_at_the_vehicle_on_screen(message: str) -> None:
    assert refers_to_current_vehicle(message) is True


@pytest.mark.parametrize("message", ["tôi muốn tư vấn xe điện", "so sánh VF 5 và VF 6", "", "cho anh xem đi"])
def test_no_pronoun_leaves_the_turn_alone(message: str) -> None:
    assert refers_to_current_vehicle(message) is False
