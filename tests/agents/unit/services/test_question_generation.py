"""Mục 5 prompt multi-slot: chống lặp câu hỏi, retry cap, fallback personalize."""

from __future__ import annotations

import pytest

from src.agents.domain.inquiry_form import VehicleInquiryForm
from src.agents.domain.values import DECLINED_SLOT_VALUE, SlotName
from src.agents.prompts.question_variants import QUESTION_VARIANTS, get_question_variant
from src.agents.services.question_generation import generate_question_for_field
from src.agents.services.slot_planning import MAX_ASK_ATTEMPTS, SlotPlanningServiceImpl


def test_every_slot_has_at_least_three_distinct_variants() -> None:
    # `BUDGET_MIN_VND` cố ý không có câu hỏi nào: nó được trích cùng lúc với trần
    # từ một câu duy nhất của khách, không bao giờ được hỏi riêng.
    for slot in SlotName:
        if slot is SlotName.INTEREST_VEHICLE:
            continue  # bối cảnh, không phải slot hỏi
        # `PURPOSE_BUCKET` cũng vậy: kết quả LLM đóng gói của `purpose`, không
        # nằm trong `SLOT_ORDER` nên không cần variant nào.
        # `BUDGET_STATED_VND` cùng nhóm: con số khách nói ra, giữ lại CHỈ để nhắc
        # lại đúng lời họ (Sếp 2026-08-25). Không lọc, không hỏi, không variant.
        # `REGISTRATION_PROVINCE` (2026-08-26) cùng nhóm "không bao giờ hỏi":
        # tỉnh đăng ký suy từ vị trí trình duyệt và khách sửa được ngay dưới bảng
        # chi phí, nên nó không có câu hỏi nào để mà cần biến thể.
        if slot in {
            SlotName.BUDGET_MIN_VND,
            SlotName.PURPOSE_BUCKET,
            SlotName.BUDGET_STATED_VND,
            SlotName.REGISTRATION_PROVINCE,
        }:
            continue
        variants = QUESTION_VARIANTS[slot]
        assert len(variants) >= 3, slot
        assert len(set(variants)) == len(variants), slot


def test_asking_the_same_field_three_times_never_repeats_a_sentence() -> None:
    """Lặp y nguyên câu hỏi làm khách tưởng agent hỏng — mục 3.1."""

    asked = [get_question_variant(SlotName.BUDGET_MAX_VND, retry) for retry in range(3)]

    assert len(set(asked)) == 3
    assert all(first != second for first, second in zip(asked, asked[1:], strict=False))


def test_first_variant_is_unchanged_so_only_retries_are_affected() -> None:
    """Lượt hỏi ĐẦU phải giữ nguyên câu cũ: thay đổi này chỉ nhắm vào hỏi lại."""

    assert get_question_variant(SlotName.BUDGET_MAX_VND, 0) == "Anh/chị dự tính khoảng bao nhiêu cho chiếc xe này ạ?"


def test_vehicle_elimination_gets_a_complete_acknowledgment_before_budget() -> None:
    planner = SlotPlanningServiceImpl()

    question = planner.question_for_turn(
        slot=SlotName.BUDGET_MAX_VND,
        retry_count=0,
        user_message="Tôi đang cân nhắc VF 5 và VF 7, nhưng loại VF 5 vì hơi chật.",
        vehicle_mentions=["VF 5", "VF 7"],
    )

    assert question == (
        "Em đã ghi nhận anh/chị loại VF 5 vì hơi chật và đang cân nhắc VF 7. "
        "Anh/chị dự tính ngân sách khoảng bao nhiêu ạ?"
    )


def test_vehicle_acknowledgment_is_not_repeated_on_a_budget_retry() -> None:
    planner = SlotPlanningServiceImpl()

    question = planner.question_for_turn(
        slot=SlotName.BUDGET_MAX_VND,
        retry_count=1,
        user_message="Tôi loại VF 5 và giữ lại VF 7.",
        vehicle_mentions=["VF 5", "VF 7"],
    )

    assert question == get_question_variant(SlotName.BUDGET_MAX_VND, 1)


def test_vehicle_acknowledgment_does_not_repeat_the_following_selection_clause() -> None:
    planner = SlotPlanningServiceImpl()

    question = planner.question_for_turn(
        slot=SlotName.BUDGET_MAX_VND,
        retry_count=0,
        user_message="Tôi loại VF 5 vì chật và giữ lại VF 7.",
        vehicle_mentions=["VF 5", "VF 7"],
    )

    assert question == (
        "Em đã ghi nhận anh/chị loại VF 5 vì chật và đang cân nhắc VF 7. Anh/chị dự tính ngân sách khoảng bao nhiêu ạ?"
    )


def test_positive_selection_without_an_elimination_keeps_the_generic_question() -> None:
    planner = SlotPlanningServiceImpl()

    question = planner.question_for_turn(
        slot=SlotName.BUDGET_MAX_VND,
        retry_count=0,
        user_message="Tôi đang cân nhắc VF 5 và VF 7.",
        vehicle_mentions=["VF 5", "VF 7"],
    )

    assert question == get_question_variant(SlotName.BUDGET_MAX_VND, 0)


def test_question_for_turn_uses_llm_rejected_mention_when_it_matches() -> None:
    planner = SlotPlanningServiceImpl()

    question = planner.question_for_turn(
        slot=SlotName.BUDGET_MAX_VND,
        retry_count=0,
        user_message="câu này không có cấu trúc regex bắt được",
        vehicle_mentions=["VF3", "VF5"],
        rejected_mention="VF3",
        rejection_reason="hết chỗ để hàng",
    )

    assert "VF3" in question and "hết chỗ để hàng" in question


def test_question_for_turn_ignores_llm_mention_not_in_this_turns_list() -> None:
    planner = SlotPlanningServiceImpl()

    question = planner.question_for_turn(
        slot=SlotName.BUDGET_MAX_VND,
        retry_count=0,
        user_message="loại VF9 nhé",
        vehicle_mentions=["VF3", "VF5"],
        rejected_mention="VF9",  # không nằm trong mentions của lượt này
        rejection_reason=None,
    )

    assert "VF9" not in question  # rơi về regex, không dùng tên LLM bịa


def test_running_out_of_variants_keeps_the_last_one_instead_of_raising() -> None:
    variants = QUESTION_VARIANTS[SlotName.PURPOSE]

    assert get_question_variant(SlotName.PURPOSE, 99) == variants[-1]


def test_first_purpose_question_lists_the_common_choices() -> None:
    """Câu hỏi mục đích lần đầu nêu sẵn lựa chọn phổ biến — câu mở không gợi ý
    khiến khách trả lời lan man, mất tín hiệu suy loại xe (giao hàng → xe máy)."""

    first = get_question_variant(SlotName.PURPOSE, 0)

    assert "đi làm" in first
    assert "giao hàng" in first
    assert "đi cá nhân" in first


def test_a_field_asked_past_the_cap_is_skipped_for_the_next_one() -> None:
    """Quá `MAX_ASK_ATTEMPTS` → bỏ qua field, KHÔNG hỏi lần nữa (mục 4)."""

    planner = SlotPlanningServiceImpl()
    known = {"vehicle_type": "CAR", "passenger_count": 4}

    without_cap = planner.next_field(vehicle_type="CAR", known_slots=known, ask_counts={})
    at_cap = planner.next_field(
        vehicle_type="CAR",
        known_slots=known,
        ask_counts={"budget_max_vnd": MAX_ASK_ATTEMPTS + 1},
    )

    assert without_cap is SlotName.BUDGET_MAX_VND
    assert at_cap is not SlotName.BUDGET_MAX_VND


def test_the_cap_does_not_mutate_the_slots_passed_in() -> None:
    """Bỏ qua khi chọn câu hỏi không được ghi đè state của người gọi."""

    planner = SlotPlanningServiceImpl()
    known = {"vehicle_type": "CAR", "passenger_count": 4}

    planner.next_field(vehicle_type="CAR", known_slots=known, ask_counts={"budget_max_vnd": 99})

    assert known == {"vehicle_type": "CAR", "passenger_count": 4}
    assert DECLINED_SLOT_VALUE not in known.values()


def test_asking_below_the_cap_still_returns_the_same_field() -> None:
    planner = SlotPlanningServiceImpl()

    slot = planner.next_field(
        vehicle_type="CAR",
        known_slots={"vehicle_type": "CAR", "passenger_count": 4},
        ask_counts={"budget_max_vnd": MAX_ASK_ATTEMPTS},
    )

    assert slot is SlotName.BUDGET_MAX_VND


class _BrokenPersonalizer:
    async def personalize(self, *, slot_name: str, form_summary: str, base_question: str) -> str:
        raise RuntimeError("LLM personalize hong")


class _BlankPersonalizer:
    async def personalize(self, *, slot_name: str, form_summary: str, base_question: str) -> str:
        return "   "


class _WorkingPersonalizer:
    async def personalize(self, *, slot_name: str, form_summary: str, base_question: str) -> str:
        return f"[ca nhan hoa] {base_question}"


@pytest.mark.asyncio
@pytest.mark.parametrize("personalizer", [_BrokenPersonalizer(), _BlankPersonalizer()])
async def test_personalize_failure_falls_back_to_the_template(personalizer: object) -> None:
    """Cá nhân hoá chỉ làm câu hỏi mượt hơn; hỏng thì KHÔNG được chặn hội thoại."""

    form = VehicleInquiryForm.from_slots({"vehicle_type": "CAR", "passenger_count": 4})

    question = await generate_question_for_field(
        slot=SlotName.BUDGET_MAX_VND,
        form=form,
        retry_count=1,
        personalizer=personalizer,  # type: ignore[arg-type]
    )

    assert question == get_question_variant(SlotName.BUDGET_MAX_VND, 1)


@pytest.mark.asyncio
async def test_personalize_is_skipped_when_no_related_field_is_known() -> None:
    question = await generate_question_for_field(
        slot=SlotName.BUDGET_MAX_VND,
        form=VehicleInquiryForm(),
        personalizer=_WorkingPersonalizer(),
    )

    assert question == get_question_variant(SlotName.BUDGET_MAX_VND, 0)


@pytest.mark.asyncio
async def test_personalize_is_used_when_context_exists() -> None:
    form = VehicleInquiryForm.from_slots({"vehicle_type": "CAR"})

    question = await generate_question_for_field(
        slot=SlotName.BUDGET_MAX_VND, form=form, personalizer=_WorkingPersonalizer()
    )

    assert question.startswith("[ca nhan hoa]")


def test_routing_question_also_has_variants() -> None:
    """Câu định tuyến không thuộc slot nào nhưng vẫn là nguồn lặp lớn nhất.

    Đo trên 103 hội thoại thật: sau khi slot đã có biến thể, 19/19 lỗi lặp còn
    lại đều là câu này.
    """

    from src.agents.prompts.question_variants import ROUTING_VARIANTS, get_routing_variant

    asked = [get_routing_variant(retry) for retry in range(3)]

    assert len(set(asked)) == 3
    assert get_routing_variant(0) == ROUTING_VARIANTS[0]
    assert get_routing_variant(99) == ROUTING_VARIANTS[-1]


def test_routing_first_variant_keeps_the_original_wording() -> None:
    from src.agents.prompts.question_variants import get_routing_variant

    first = get_routing_variant(0)

    assert "tra cứu" in first.casefold()
    assert "tư vấn" in first.casefold()


def test_the_recap_repeats_the_figure_the_customer_said_not_the_widened_bound() -> None:
    """Bug thật Sếp báo 2026-08-25: khách nói "khoảng 500 triệu", bot ghi nhận
    "ngân sách khoảng 600 triệu" — trần của dải đã nới, không phải lời khách."""

    from src.agents.services.slot_planning import _captured_recap

    recap = _captured_recap(
        {
            SlotName.BUDGET_STATED_VND: 500_000_000,
            SlotName.BUDGET_MIN_VND: 400_000_000,
            SlotName.BUDGET_MAX_VND: 600_000_000,
        }
    )

    assert "500 triệu" in recap
    assert "600 triệu" not in recap


def test_the_recap_repeats_a_customer_stated_range_as_a_range() -> None:
    """Khách tự nêu khoảng thì nhắc lại nguyên khoảng — gọi nó là "khoảng 500
    triệu" cũng là bịa ra một con số khách không nói."""

    from src.agents.services.slot_planning import _captured_recap

    recap = _captured_recap(
        {SlotName.BUDGET_MIN_VND: 400_000_000, SlotName.BUDGET_MAX_VND: 600_000_000}
    )

    assert "từ 400 triệu đến 600 triệu" in recap
