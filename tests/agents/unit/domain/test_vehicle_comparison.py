"""[COMPARE_VEHICLES] Luật chốt tập xe + nhận diện ý so sánh.

Danh sách câu trong `test_every_required_phrasing_reaches_the_compare_branch` là
bộ ca BẮT BUỘC của đặc tả, không phải bộ đầy đủ tuyệt đối: gặp cách viết mới thì
bổ sung vào đây kèm ca tương ứng ở `domain/vehicle_comparison.plan_comparison`.
"""

from __future__ import annotations

import pytest

from src.agents.domain.entity_catalog import EntityCategory, default_catalog
from src.agents.domain.fuzzy_match import all_of, match_entities
from src.agents.domain.intent_reconciliation import reconcile_intents
from src.agents.domain.values import Intent
from src.agents.domain.vehicle_comparison import (
    ComparisonOutcome,
    has_comparison_cue,
    plan_comparison,
)

CATALOG = default_catalog()


def _layer2_vehicles(message: str) -> list[str]:
    """Tên xe Lớp 2 khớp được — đúng nguồn mà `nodes/route_intent` dùng."""

    matches = match_entities(original_text=message, catalog=CATALOG)
    return [item.canonical for item in all_of(matches, EntityCategory.VEHICLE)]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("so sánh VF3 và VF5", {"VF 3", "VF 5"}),
        ("so sánh vf 3 vs vf 5", {"VF 3", "VF 5"}),
        ("vf3 hay vf5 tốt hơn", {"VF 3", "VF 5"}),
        ("vf3-vf5 khác gì nhau", {"VF 3", "VF 5"}),
        ("nên mua vf3, vf5 hay vf6", {"VF 3", "VF 5", "VF 6"}),
        ("so sánh vf3 với evo200", {"VF 3", "Evo 200"}),
        ("SO SÁNH VINFAST VF 3 VỚI vf5", {"VF 3", "VF 5"}),
        ("so sánh vf  3 và Vf5", {"VF 3", "VF 5"}),
    ],
)
def test_every_required_phrasing_reaches_the_compare_branch(message: str, expected: set[str]) -> None:
    """Chuẩn hoá tên xe là việc của Lớp 2; ở đây chỉ kiểm nó tới được nhánh so sánh."""

    names = _layer2_vehicles(message)
    plan = plan_comparison(user_message=message, vehicle_names=names)

    assert has_comparison_cue(message) is True
    assert plan.outcome is ComparisonOutcome.COMPARE
    assert set(plan.vehicle_names) == expected


def test_columns_follow_the_order_of_the_sentence_not_the_match_score() -> None:
    """Cột phải đọc theo đúng thứ tự khách hỏi, kể cả khi hai nguồn nhận diện lệch."""

    plan = plan_comparison(
        user_message="so sánh VF 5 với VF 3",
        # Thứ tự đảo, đúng như Lớp 2 trả về (xếp theo điểm khớp giảm dần).
        vehicle_names=["VF 3", "VF 5"],
    )

    assert plan.vehicle_names == ("VF 5", "VF 3")


def test_the_same_model_typed_twice_never_reaches_the_tool() -> None:
    """Lớp 2 khử trùng theo canonical nên phải đếm trên câu gốc mới thấy trùng."""

    message = "so sánh vf3 và vf3"
    plan = plan_comparison(user_message=message, vehicle_names=_layer2_vehicles(message))

    assert plan.outcome is ComparisonOutcome.DUPLICATE_VEHICLE
    assert plan.should_call_tool is False


def test_more_than_three_models_is_refused_instead_of_truncated() -> None:
    """Cắt bớt hộ khách là tự chọn xe cho họ — đúng thứ A4-1 cấm."""

    message = "so sánh vf3, vf5, vf6 và vf7"
    plan = plan_comparison(user_message=message, vehicle_names=_layer2_vehicles(message))

    assert plan.outcome is ComparisonOutcome.TOO_MANY_VEHICLES
    assert plan.requested_count == 4
    assert plan.should_call_tool is False


def test_one_model_plus_a_compare_word_falls_back_instead_of_comparing() -> None:
    message = "so sánh VF3 xem sao"
    plan = plan_comparison(user_message=message, vehicle_names=_layer2_vehicles(message))

    assert plan.outcome is ComparisonOutcome.NEED_MORE_VEHICLES
    assert plan.vehicle_names == ("VF 3",)


def test_two_models_without_a_comparison_question_stay_a_lookup() -> None:
    """ "giá VF3 và VF5 bao nhiêu" là hai câu tra cứu, không phải một bảng."""

    message = "giá vf3 và vf5 bao nhiêu"
    plan = plan_comparison(user_message=message, vehicle_names=_layer2_vehicles(message))

    assert has_comparison_cue(message) is False
    assert plan.outcome is ComparisonOutcome.NOT_A_COMPARISON


@pytest.mark.parametrize(
    "message",
    [
        "so sánh VF3 và VF5",
        "vf3 hay vf5 tốt hơn",
        "nên mua vf3, vf5 hay vf6",
    ],
)
def test_reconciliation_labels_the_turn_compare_and_drops_lookup(message: str) -> None:
    """`state["intents"]` là nguồn sự thật; nhãn phải tất định, không do LLM phát."""

    intents = reconcile_intents(
        user_message=message,
        # Bộ trích LLM gắn nhãn cũ — bộ hoà giải phải sửa lại.
        raw_intents=[Intent.CATALOG_LOOKUP, Intent.ADVISORY],
        normalized_slots={},
        vehicle_mentions=_layer2_vehicles(message),
    )

    assert intents == [Intent.COMPARE_VEHICLES]


def test_reconciliation_keeps_the_old_label_when_only_one_model_is_named() -> None:
    intents = reconcile_intents(
        user_message="so sánh VF3 xem sao",
        raw_intents=[Intent.CATALOG_LOOKUP],
        normalized_slots={},
        vehicle_mentions=["VF 3"],
    )

    assert Intent.COMPARE_VEHICLES not in intents
    assert Intent.CATALOG_LOOKUP in intents
