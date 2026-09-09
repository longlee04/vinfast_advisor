from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.values import (
    DialogueAct,
    Intent,
    ScopeLabel,
    SlotName,
    TaskAction,
    VehicleType,
)
from src.agents.services.slot_extraction import SlotExtractionServiceImpl, _parse_budget
from src.agents.services.slot_planning import SlotPlanningServiceImpl


class FakeLLM:
    def __init__(self, payload: LLMExtractionPayload) -> None:
        self.payload = payload

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
        return self.payload

    async def synthesize(self, *, prompt: str) -> str:
        return prompt


class RecordingLLM(FakeLLM):
    def __init__(self, payload: LLMExtractionPayload) -> None:
        super().__init__(payload)
        self.extraction_kwargs: dict[str, object] = {}

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
        self.extraction_kwargs = kwargs
        return self.payload


@dataclass
class Pending:
    values: list[str]

    async def record(self, session_id: str, customer_id: str, mentions: list[str]) -> None:
        self.values.extend(mentions)

    async def get_pending(self, session_id: str) -> list[str]:
        return list(self.values)

    async def clear(self, session_id: str) -> None:
        self.values.clear()

    async def consume(self, session_id: str, customer_id: str) -> list[str]:
        values = list(self.values)
        self.values.clear()
        return values


@dataclass
class Sessions:
    """Fake trong bộ nhớ cho `SessionRepository` — `extract` ghi slot ngay khi trích xuất."""

    ensured: list[tuple[str, str]]
    upserts: dict[SlotName, object]

    async def ensure_session(self, session_id: str, customer_id: str, vehicle_type_hint: object) -> None:
        self.ensured.append((session_id, customer_id))

    async def get_slots(self, session_id: str, customer_id: str) -> dict:
        return dict(self.upserts)

    async def upsert_slot(self, session_id: str, slot_name: SlotName, value: object) -> None:
        # NGHIÊM: repository thật đọc `slot_name.value`, nên một chuỗi lọt vào đây
        # làm nổ cả lượt với `AttributeError: 'str' object has no attribute 'value'`.
        # Bug thật 2026-08-27, và fake cũ nuốt gọn vì `SlotName` là `StrEnum` —
        # một `str` trông y hệt một thành viên enum với cả `==` lẫn mypy.
        assert isinstance(slot_name, SlotName), f"khoa slot phai la SlotName, nhan duoc {slot_name!r}"
        self.upserts[slot_name] = value


@dataclass
class Transaction:
    pending_mentions: Pending
    sessions: Sessions


class Uow:
    def __init__(self, pending: Pending, sessions: Sessions | None = None) -> None:
        self.transaction_value = Transaction(pending, sessions or Sessions([], {}))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        yield self.transaction_value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("700 triệu", 700_000_000), ("1 tỷ 2", 1_200_000_000), ("1ty2", 1_200_000_000), ("700tr", 700_000_000)],
)
def test_parse_budget_variants(raw: str, expected: int) -> None:
    assert _parse_budget(raw) == expected


@pytest.mark.asyncio
async def test_extract_normalizes_vietnamese_budget_and_keeps_intents() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(budget_max_vnd="1 tỷ 2", intents=[Intent.ADVISORY])), Uow(Pending([]))
    )

    result = await service.extract(
        session_id="s", customer_id="customer", vehicle_type=VehicleType.CAR, user_message="x"
    )

    assert result.slots[SlotName.BUDGET_MAX_VND] == Decimal("1_200_000_000")
    assert result.intents == [Intent.ADVISORY]


@pytest.mark.asyncio
async def test_extract_reconciles_missing_advisory_without_another_llm_call() -> None:
    llm = RecordingLLM(
        LLMExtractionPayload(
            vehicle_type=VehicleType.CAR,
            passenger_count=4,
            budget_max_vnd="500 triệu",
            vehicle_name_mentions=["VF 5"],
            intents=[Intent.CATALOG_LOOKUP],
        )
    )
    service = SlotExtractionServiceImpl(llm, Uow(Pending([])))

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Nhà tôi bốn người, khoảng 500 triệu; VF 5 có hợp không?",
    )

    assert result.intents == [Intent.ADVISORY, Intent.CATALOG_LOOKUP]


@pytest.mark.asyncio
async def test_named_model_listing_recovers_from_false_browse_intent() -> None:
    """The real extraction path must prefer recovered model identity over a raw browse label."""

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(intents=[Intent.CATALOG_BROWSE])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="tất cả các mẫu vf8 hiện tại",
    )

    assert result.vehicle_name_mentions == ["VF 8"]
    assert result.intents == [Intent.CATALOG_LOOKUP]


@pytest.mark.asyncio
async def test_extracts_explicit_car_type_when_llm_omits_it() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(home_charging=False, intents=[Intent.ADVISORY])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Tôi ở chung cư, vậy có nên mua ô tô điện không?",
    )

    assert result.slots[SlotName.VEHICLE_TYPE] == VehicleType.CAR.value


@pytest.mark.asyncio
async def test_extracts_explicit_usage_tags_when_llm_omits_them() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                purpose="chủ yếu đi nội thành và thỉnh thoảng về quê",
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Chủ yếu đi nội thành và thỉnh thoảng về quê.",
    )

    assert result.slots[SlotName.HABIT_NEED_TAGS] == [
        "đi nội thành",
        "thỉnh thoảng về quê",
    ]


@pytest.mark.asyncio
async def test_extracts_explicit_commute_purpose_when_llm_omits_it() -> None:
    service = SlotExtractionServiceImpl(FakeLLM(LLMExtractionPayload()), Uow(Pending([])))

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        user_message="de di lam, ngan sach 30 trieu",
    )

    assert result.slots[SlotName.PURPOSE] == "di lam"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_count"),
    [("Tôi cần xe 5 chỗ", 5), ("Mình đang tìm ô tô 7 cho", 7)],
)
async def test_first_turn_keeps_an_explicit_seat_request_when_llm_omits_it(message: str, expected_count: int) -> None:
    service = SlotExtractionServiceImpl(FakeLLM(LLMExtractionPayload(intents=[Intent.ADVISORY])), Uow(Pending([])))

    result = await service.extract(session_id="s", customer_id="customer", vehicle_type=None, user_message=message)

    assert result.slots[SlotName.VEHICLE_TYPE] == VehicleType.CAR.value
    assert result.slots[SlotName.PASSENGER_COUNT] == expected_count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "Tôi không cần xe 7 chỗ",
        "Không phải loại 7 chỗ nhé",
        "Tôi đang phân vân giữa xe 5 chỗ và 7 chỗ",
        "Xe 5 chỗ có rộng bằng xe 7 chỗ không?",
    ],
)
async def test_does_not_treat_negated_or_ambiguous_seat_mentions_as_a_need(
    message: str,
) -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(passenger_count=7, intents=[Intent.ADVISORY])),
        Uow(Pending([])),
    )

    result = await service.extract(session_id="s", customer_id="customer", vehicle_type=None, user_message=message)

    assert SlotName.PASSENGER_COUNT not in result.slots
    assert SlotName.VEHICLE_TYPE not in result.slots


@pytest.mark.asyncio
async def test_question_about_a_seat_category_is_not_treated_as_a_confirmed_need() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(passenger_count=5, intents=[Intent.CATALOG_LOOKUP])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Xe 5 chỗ thế nào?",
    )

    assert SlotName.PASSENGER_COUNT not in result.slots


@pytest.mark.asyncio
async def test_prefers_an_affirmed_seat_count_after_a_negated_alternative() -> None:
    service = SlotExtractionServiceImpl(FakeLLM(LLMExtractionPayload(intents=[Intent.ADVISORY])), Uow(Pending([])))

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Không cần 7 chỗ, 5 chỗ là đủ",
    )

    assert result.slots[SlotName.VEHICLE_TYPE] == VehicleType.CAR.value
    assert result.slots[SlotName.PASSENGER_COUNT] == 5


@pytest.mark.asyncio
async def test_explicit_seat_request_is_not_asked_again_by_the_slot_planner() -> None:
    service = SlotExtractionServiceImpl(FakeLLM(LLMExtractionPayload(intents=[Intent.ADVISORY])), Uow(Pending([])))

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Tôi cần xe 7 chỗ",
    )
    question = SlotPlanningServiceImpl().next_question(
        vehicle_type=VehicleType.CAR.value,
        known_slots=result.slots,
    )

    assert question is not None
    assert "mấy người" not in question


@pytest.mark.asyncio
async def test_standalone_number_uses_the_budget_slot_currently_waiting_for_an_answer() -> None:
    llm = RecordingLLM(LLMExtractionPayload(intents=[Intent.ADVISORY]))
    sessions = Sessions([], {SlotName.VEHICLE_TYPE: VehicleType.CAR.value})
    service = SlotExtractionServiceImpl(llm, Uow(Pending([]), sessions))

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="5",
    )

    # Sếp chốt 2026-08-28: một chữ số không đoán triệu/tỷ — tầng pending slot hỏi lại đơn vị.
    assert SlotName.BUDGET_MAX_VND not in result.slots
    assert "budget_max_vnd" in str(llm.extraction_kwargs["conversation_history"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vehicle_type", "payload", "forbidden_slot"),
    [
        (
            VehicleType.CAR,
            LLMExtractionPayload(vehicle_type=VehicleType.CAR, max_load_kg=80),
            SlotName.MAX_LOAD_KG,
        ),
        (
            VehicleType.ELECTRIC_MOTORBIKE,
            LLMExtractionPayload(vehicle_type=VehicleType.ELECTRIC_MOTORBIKE, passenger_count=5),
            SlotName.PASSENGER_COUNT,
        ),
    ],
)
async def test_extraction_discards_a_branch_specific_slot_for_the_wrong_vehicle_type(
    vehicle_type: VehicleType,
    payload: LLMExtractionPayload,
    forbidden_slot: SlotName,
) -> None:
    service = SlotExtractionServiceImpl(FakeLLM(payload), Uow(Pending([])))

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=vehicle_type,
        user_message="x",
    )

    assert forbidden_slot not in result.slots


@pytest.mark.asyncio
async def test_malformed_runtime_payload_does_not_record_pending_mentions() -> None:

    pending = Pending([])
    service = SlotExtractionServiceImpl(
        FakeLLM({"passenger_count": "bad", "vehicle_name_mentions": ["VF 8"]}), Uow(pending)
    )

    with pytest.raises(ValidationError):
        await service.extract(session_id="s", customer_id="customer", vehicle_type=None, user_message="x")

    assert pending.values == []


@pytest.mark.asyncio
async def test_invalid_budget_is_ignored_and_does_not_record_pending_mentions() -> None:
    pending = Pending([])
    service = SlotExtractionServiceImpl(
        FakeLLM({"budget_max_vnd": -1, "vehicle_name_mentions": ["VF 8"]}), Uow(pending)
    )

    result = await service.extract(session_id="s", customer_id="customer", vehicle_type=None, user_message="x")

    assert SlotName.BUDGET_MAX_VND not in result.slots
    assert pending.values == []


@pytest.mark.asyncio
async def test_monthly_installment_is_not_stored_as_total_vehicle_budget() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                budget_max_vnd="10 triệu",
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Tôi chỉ trả góp được 10 triệu mỗi tháng.",
    )

    assert SlotName.BUDGET_MAX_VND not in result.slots


@pytest.mark.asyncio
async def test_home_charging_requires_explicit_charging_language() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                home_charging=False,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Tôi cần ô tô điện.",
    )

    assert SlotName.HOME_CHARGING not in result.slots


@pytest.mark.asyncio
async def test_explicit_charging_constraint_is_kept() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                home_charging=False,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Chung cư không cho sạc dưới hầm.",
    )

    assert result.slots[SlotName.HOME_CHARGING] is False


@pytest.mark.asyncio
async def test_pure_catalog_question_never_writes_need_slots_from_model_digits() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                passenger_count=5,
                required_range_km=10,
                vehicle_name_mentions=["VF 5"],
                intents=[Intent.CATALOG_LOOKUP],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="VF 5 của tôi pin tụt sau 10 km, xe bị sao?",
    )

    assert result.slots == {}


@pytest.mark.asyncio
async def test_selection_turn_drops_passenger_count_hallucinated_from_model_name() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                passenger_count=5,
                vehicle_name_mentions=["VF 5", "VF 7"],
                intents=[],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Tôi đang cân nhắc VF 5 và VF 7, nhưng loại VF 5 vì hơi chật.",
    )

    assert result.slots == {SlotName.VEHICLE_TYPE: "CAR"}
    assert result.intents == [Intent.ADVISORY]
    assert result.vehicle_name_mentions == ["VF 5", "VF 7"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "model_count"),
    [
        ("Tôi đang xem VF 7.", 7),
        ("Tôi đang cân nhắc VF 8.", 8),
        ("Tôi quan tâm VF e34.", 34),
    ],
)
async def test_model_number_without_people_or_seat_unit_never_fills_passenger_count(
    message: str,
    model_count: int,
) -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                passenger_count=model_count,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message=message,
    )

    assert SlotName.PASSENGER_COUNT not in result.slots


@pytest.mark.asyncio
async def test_explicit_people_count_is_kept_when_a_model_number_is_also_present() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                passenger_count=5,
                vehicle_name_mentions=["VF 7"],
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Nhà tôi 5 người và đang cân nhắc VF 7.",
    )

    assert result.slots[SlotName.PASSENGER_COUNT] == 5


@pytest.mark.asyncio
async def test_family_member_count_is_valid_passenger_evidence() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                passenger_count=4,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Tìm xe cho gia đình 4 thành viên.",
    )

    assert result.slots[SlotName.PASSENGER_COUNT] == 4


@pytest.mark.asyncio
async def test_comparison_recovers_vf_mentions_and_lookup_when_llm_omits_both() -> None:
    """[COMPARE_VEHICLES] Nhãn cũ ở đây là `CATALOG_LOOKUP`, giờ là so sánh.

    Điều bài test canh không đổi: bộ trích LLM bỏ sót cả tên xe lẫn intent, và bộ
    hoà giải tất định phải dựng lại đủ cả hai mà không gọi mô hình lần nữa.
    """

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(vehicle_type=VehicleType.CAR)),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="VF 5 và VF 7 khác nhau thế nào?",
    )

    assert result.slots == {}
    assert result.intents == [Intent.COMPARE_VEHICLES]
    assert result.vehicle_name_mentions == ["VF 5", "VF 7"]


@pytest.mark.asyncio
async def test_vf_fallback_deduplicates_compact_llm_mentions() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(vehicle_name_mentions=["vf5"], intents=[Intent.CATALOG_LOOKUP])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="VF5 và VF 7 khác nhau thế nào?",
    )

    assert result.vehicle_name_mentions == ["VF 5", "VF 7"]


@pytest.mark.asyncio
async def test_vague_message_cannot_flip_an_existing_vehicle_branch() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
                habit_need_tags=["tiết kiệm"],
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="Em ưu tiên xe tiết kiệm, dễ đi trong phố.",
    )

    assert SlotName.VEHICLE_TYPE not in result.slots
    assert result.slots[SlotName.HABIT_NEED_TAGS] == ["tiết kiệm"]


@pytest.mark.asyncio
async def test_only_feature_mentions_are_persisted_as_pending() -> None:
    pending = Pending([])
    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(feature_mentions=["cửa sổ trời"], vehicle_name_mentions=["VF 8"])),
        Uow(pending),
    )

    await service.extract(session_id="s", customer_id="c", vehicle_type=None, user_message="x")

    # Chữ tự do được QUY VỀ mã tập đóng (Sếp 2026-08-26): `scoring` so theo
    # `feature_code`, nên giữ nguyên "cửa sổ trời" là giữ một thứ không góp được
    # điểm nào — im lặng, đúng bẫy mục 3.4.
    assert pending.values == ["PANORAMIC_ROOF"]


@pytest.mark.asyncio
async def test_vehicle_name_mentions_reach_state_without_touching_pending_table() -> None:
    pending = Pending([])
    service = SlotExtractionServiceImpl(FakeLLM(LLMExtractionPayload(vehicle_name_mentions=["VF 9"])), Uow(pending))

    result = await service.extract(session_id="s", customer_id="c", vehicle_type=None, user_message="VF 9")

    assert result.vehicle_name_mentions == ["VF 9"]
    assert pending.values == []


@pytest.mark.asyncio
async def test_short_model_followup_recovers_lookup_when_llm_omits_intent_and_entity() -> None:
    """`VF9 đi` must not depend on the model treating a discourse particle as a lookup cue."""

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.IN_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                intents=[],
                vehicle_name_mentions=[],
            )
        ),
        Uow(Pending([]), Sessions([], {SlotName.VEHICLE_TYPE: "CAR"})),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="vf9 đi",
    )

    assert result.vehicle_name_mentions == ["VF 9"]
    assert result.intents == [Intent.CATALOG_LOOKUP]
    assert result.task_action is TaskAction.START_NEW_TASK


@pytest.mark.asyncio
async def test_extract_records_then_consumes_pending_mentions() -> None:
    pending = Pending([])
    service = SlotExtractionServiceImpl(FakeLLM(LLMExtractionPayload(feature_mentions=["cửa sổ trời"])), Uow(pending))

    await service.extract(session_id="s", customer_id="customer", vehicle_type=None, user_message="x")

    assert await service.consume_pending("s", "customer") == ["PANORAMIC_ROOF"]
    assert await service.consume_pending("s", "customer") == []


@pytest.mark.asyncio
async def test_named_family_listing_overrides_stale_advisory_and_legacy_missing_label() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.MISSING_DATA,
                dialogue_act=DialogueAct.REQUEST,
                task_action=TaskAction.CONTINUE_TASK,
                intents=[Intent.CATALOG_BROWSE],
            )
        ),
        Uow(Pending([]), Sessions([], {SlotName.BUDGET_MAX_VND: 500_000_000})),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="tất cả các mẫu VF8",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": "2026-08-19T00:00:00+00:00",
        },
    )

    assert result.scope is ScopeLabel.IN_SCOPE
    assert result.intents == [Intent.CATALOG_LOOKUP]
    assert result.vehicle_name_mentions == ["VF 8"]
    assert result.task_action is TaskAction.INTERRUPT_WITH_LOOKUP


@pytest.mark.asyncio
async def test_vehicle_name_does_not_force_an_unrelated_action_into_scope() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.OUT_OF_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                intents=[Intent.CATALOG_LOOKUP],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="tôi muốn đi tù bằng VF8",
    )

    assert result.scope is ScopeLabel.OUT_OF_SCOPE
    assert result.intents == []
    assert result.vehicle_name_mentions == []


@pytest.mark.asyncio
async def test_generic_other_vehicle_request_browses_without_old_exclusions() -> None:
    first = "10000000-0000-0000-0000-000000000001"
    second = "10000000-0000-0000-0000-000000000002"
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.IN_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                task_action=TaskAction.CONTINUE_TASK,
                vehicle_type=VehicleType.CAR,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="tôi muốn tư vấn xe khác",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": [first, second]},
            "revision": 1,
            "updated_at": "2026-08-19T00:00:00+00:00",
        },
    )

    assert result.intents == [Intent.CATALOG_BROWSE]
    assert result.task_action is TaskAction.INTERRUPT_WITH_LOOKUP
    assert result.excluded_vehicle_ids == ()


@pytest.mark.asyncio
async def test_generic_advisory_after_completed_result_browses_instead_of_clarifying() -> None:
    """A vague vehicle request lists products instead of replaying or asking three choices."""

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.IN_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                task_action=TaskAction.CONTINUE_TASK,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([]), Sessions([], {SlotName.BUDGET_MAX_VND: 500_000_000})),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="tôi muốn tư vấn xe",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": "2026-08-19T00:00:00+00:00",
        },
    )

    assert result.intents == [Intent.CATALOG_BROWSE]
    assert result.task_action is TaskAction.INTERRUPT_WITH_LOOKUP


@pytest.mark.asyncio
async def test_generic_vehicle_advisory_uses_catalog_not_old_scoring_slots() -> None:
    """A repeated CAR branch scopes browse cards but does not rerun completed scoring."""

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.IN_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                task_action=TaskAction.CONTINUE_TASK,
                vehicle_type=VehicleType.CAR,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(
            Pending([]),
            Sessions(
                [],
                {
                    SlotName.VEHICLE_TYPE: "CAR",
                    SlotName.BUDGET_MAX_VND: 500_000_000,
                    SlotName.PASSENGER_COUNT: 5,
                },
            ),
        ),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="tôi muốn tư vấn xe",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": "2026-08-19T00:00:00+00:00",
        },
    )

    assert result.intents == [Intent.CATALOG_BROWSE]
    assert result.task_action is TaskAction.INTERRUPT_WITH_LOOKUP


@pytest.mark.asyncio
async def test_short_continue_answer_resumes_the_completed_advisory() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.IN_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                task_action=TaskAction.CONTINUE_TASK,
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="tiếp tục",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": "2026-08-19T00:00:00+00:00",
        },
    )

    assert result.task_action is TaskAction.RESUME_TASK


@pytest.mark.asyncio
async def test_named_model_consultation_interrupts_stale_advisory_with_targeted_lookup() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.IN_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                task_action=TaskAction.CONTINUE_TASK,
                vehicle_type=VehicleType.CAR,
                vehicle_name_mentions=["VF 5"],
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(
            Pending([]),
            Sessions(
                [],
                {
                    SlotName.VEHICLE_TYPE: "CAR",
                    SlotName.BUDGET_MAX_VND: 500_000_000,
                    SlotName.PASSENGER_COUNT: 4,
                },
            ),
        ),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="tôi muốn tư vấn xe VF5",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": "2026-08-19T00:00:00+00:00",
        },
    )

    assert result.intents == [Intent.CATALOG_LOOKUP]
    assert result.vehicle_name_mentions == ["VF 5"]
    assert result.slots == {}
    assert result.task_action is TaskAction.INTERRUPT_WITH_LOOKUP


@pytest.mark.asyncio
async def test_first_catalog_lookup_starts_a_task_instead_of_claiming_an_interruption() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                scope=ScopeLabel.IN_SCOPE,
                dialogue_act=DialogueAct.REQUEST,
                task_action=TaskAction.INTERRUPT_WITH_LOOKUP,
                vehicle_name_mentions=["VF 8"],
                intents=[Intent.CATALOG_LOOKUP],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="giá VF8 bao nhiêu?",
    )

    assert result.task_action is TaskAction.START_NEW_TASK


@pytest.mark.asyncio
async def test_extract_returns_feature_mentions_for_the_same_turn() -> None:
    """Tính năng khách vừa chọn (lượt 2) phải về kịp lượt NÀY: đề xuất chạy
    trong chính lượt đó, chờ pending table tiêu thụ ở lượt sau là mất tín hiệu."""

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                feature_mentions=["HIGH_PAYLOAD"],
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="Tôi thích xe tải trọng lớn.",
    )

    assert result.feature_mentions == ["HIGH_PAYLOAD"]


@pytest.mark.asyncio
async def test_implausible_daily_range_is_not_written_and_reports_the_reason() -> None:
    """T2 Lớp 3: "mỗi ngày 500 km" → KHÔNG ghi slot, trả lý do để lượt này phát
    câu xác nhận đơn vị (design doc Success Criteria)."""

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                required_range_km=500,
                range_period="day",
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Mỗi ngày tôi chạy khoảng 500 km.",
    )

    assert SlotName.REQUIRED_RANGE_KM not in result.slots
    assert result.range_clarify_reason == "daily_km_above_ceiling"


@pytest.mark.asyncio
async def test_trip_period_range_is_not_converted_and_reports_the_reason() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                required_range_km=80,
                range_period="trip",
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Mỗi chuyến tôi chạy 80 km.",
    )

    assert SlotName.REQUIRED_RANGE_KM not in result.slots
    assert result.range_clarify_reason == "trip_period_needs_confirmation"


@pytest.mark.asyncio
async def test_monthly_range_is_converted_without_a_clarify_reason() -> None:
    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                required_range_km=1200,
                range_period="month",
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Tháng khoảng 1200 km.",
    )

    assert result.slots[SlotName.REQUIRED_RANGE_KM] == 40
    assert result.range_clarify_reason is None


@pytest.mark.asyncio
async def test_pure_catalog_lookup_drops_the_range_clarify_reason() -> None:
    """Lượt chỉ tra cứu không phải đang khai nhu cầu → không hỏi xác nhận đơn vị."""

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                required_range_km=500,
                range_period="day",
                vehicle_name_mentions=["VF 5"],
                intents=[Intent.CATALOG_LOOKUP],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="VF 5 chạy được bao xa?",
    )

    assert result.slots == {}
    assert result.range_clarify_reason is None


def test_llm_extraction_payload_accepts_closed_purpose_bucket() -> None:
    from src.agents.domain.slot_mapping import PurposeBucket

    payload = LLMExtractionPayload.model_validate({"purpose_bucket": "family"})
    assert payload.purpose_bucket is PurposeBucket.FAMILY


def test_llm_extraction_payload_drops_unknown_purpose_bucket_but_keeps_the_rest() -> None:
    # Prod 2026-08-29: một nhãn lạ từng làm VỨT cả payload (146 lần / 3 ngày) — nay chỉ bỏ nhãn đó.
    payload = LLMExtractionPayload.model_validate({"purpose_bucket": "khong_hop_le", "budget_max_vnd": "700 triệu"})
    assert payload.purpose_bucket is None
    assert payload.budget_max_vnd == "700 triệu"


@pytest.mark.asyncio
async def test_extract_persists_purpose_bucket_when_llm_provides_it() -> None:
    from src.agents.domain.slot_mapping import PurposeBucket

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                vehicle_type=VehicleType.CAR,
                purpose="chở gia đình đi làm",
                purpose_bucket=PurposeBucket.FAMILY,
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="Tôi cần xe chở gia đình đi làm.",
    )

    assert result.slots[SlotName.PURPOSE_BUCKET] == "family"


@pytest.mark.asyncio
async def test_nhan_tap_dong_llm_tra_ve_duoc_luu_bang_ten_tieng_viet() -> None:
    """LLM nay chọn `habit_need_tags` trong tập đóng `NeedTag`. Slot vẫn phải
    đọc được như lời người: nó đi thẳng vào prompt tổng hợp qua
    `nodes/synthesize._customer_wording`, mà mã thô ở đó làm vỡ pitch (bẫy 3.9).
    """

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(habit_need_tags=["URBAN_TRAFFIC"], intents=[Intent.ADVISORY])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="anh chỉ cần 1 chiếc nhỏ gọn thôi",
    )

    assert result.slots[SlotName.HABIT_NEED_TAGS] == ["Đi lại nội thành"]


@pytest.mark.asyncio
async def test_chu_tu_do_cua_phien_cu_van_duoc_giu_nguyen_khong_bi_bia_nhan() -> None:
    """Đường cũ phải sống: `_explicit_habit_need_tags` vẫn ghi chữ tự do bằng
    regex tất định, và slot cũ trong `conversation_slots` cũng là chữ tự do."""

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(habit_need_tags=["hay chở con nhỏ"], intents=[Intent.ADVISORY])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="nhà anh hay chở con nhỏ",
    )

    assert result.slots[SlotName.HABIT_NEED_TAGS] == ["hay chở con nhỏ"]


@pytest.mark.asyncio
async def test_travel_habit_answers_the_purpose_question() -> None:
    """Đã nói đi đâu thì đừng hỏi lại mục đích.

    BUG PROD 2026-08-26, phiên `53d8366f`. Khách gõ *"anh có khoảng 500 triệu và
    muốn 1 chiếc xe nhỏ gọn đi trong nội thành"*; slot về `habit_need_tags =
    ["Đi lại nội thành"]` còn `purpose` RỖNG, nên cụm hỏi mở đầu (ngân sách +
    mục đích) vẫn còn một mục thiếu và lượt ấy trả về *"anh/chị mua xe để dùng
    vào mục đích gì ạ"* — hỏi lại đúng điều khách vừa nói, KHÔNG xe nào ra.
    """

    service = SlotExtractionServiceImpl(
        FakeLLM(
            LLMExtractionPayload(
                habit_need_tags=["Đi lại nội thành"],
                intents=[Intent.ADVISORY],
            )
        ),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="anh có khoảng 500 triệu và muốn 1 chiếc xe nhỏ gọn đi trong nội thành",
    )

    assert result.slots[SlotName.PURPOSE] == "Đi lại nội thành"


@pytest.mark.asyncio
async def test_a_car_preference_is_not_promoted_to_a_purpose() -> None:
    """`COMPACT_SIZE` tả xe trông thế nào, không tả khách dùng xe làm gì."""

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(habit_need_tags=["COMPACT_SIZE"], intents=[Intent.ADVISORY])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="anh cần 1 chiếc nhỏ gọn thôi",
    )

    assert SlotName.PURPOSE not in result.slots


@pytest.mark.asyncio
async def test_province_and_daily_distance_count_as_new_task_information() -> None:
    """Bộ đọc tất định phải lên tiếng TRƯỚC khi bộ định tuyến chốt.

    BUG PROD 2026-08-26, phiên `b33300cc`. Sau khi khách chọn xe xong, họ gõ
    *"anh ở hồ chí minh và đi khoảng 50km 1 ngày"* — đúng hai thông tin bảng chi
    phí cần. LLM trả `slots_gained = {}` (đo trong `turn_traces.payload->llm`),
    nên `_has_new_task_information` trả False và lượt rơi vào `CLARIFY_TASK`:
    *"cho em biết ngân sách hoặc số chỗ ngồi mong muốn nhé"* — hỏi lại ngân sách
    đã có, và hỏi số chỗ, thứ luồng này đã bỏ hẳn không hỏi.
    """

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(intents=[Intent.ADVISORY])),
        Uow(Pending([]), Sessions([], {SlotName.BUDGET_MAX_VND: 700_000_000})),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="anh ở hồ chí minh và đi khoảng 50km 1 ngày",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": "2026-08-26T00:00:00+00:00",
        },
    )

    assert result.slots[SlotName.REGISTRATION_PROVINCE] == "HCM"
    assert result.slots[SlotName.REQUIRED_RANGE_KM] == 50
    assert result.task_action is not TaskAction.CLARIFY_TASK


@pytest.mark.asyncio
async def test_an_out_of_scope_question_does_not_pick_up_a_province() -> None:
    """ "Hôm nay thời tiết Hà Nội thế nào?" không phải lượt tư vấn — không nhặt tỉnh."""

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(intents=[])),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=None,
        user_message="Hôm nay thời tiết Hà Nội thế nào?",
    )

    assert SlotName.REGISTRATION_PROVINCE not in result.slots


@pytest.mark.asyncio
async def test_a_smaller_car_request_revises_the_results_instead_of_dying() -> None:
    """Đúng câu đã hỏng hai kiểu khác nhau trên prod 2026-08-26.

    `payload->llm` thật của cả hai lần: `intents: []`, `slots_gained: {}` — mô
    hình không hiểu gì. Phiên `705dd9ca` nhận `OUT_OF_SCOPE` (lượt chết); phiên
    `1e9ec5c3` nhận `IN_SCOPE` rồi đề xuất lại chính **VF 8** khách vừa chê to.

    Ba điều phải cùng đúng thì lượt mới đi đúng hướng:
    lượt là ADVISORY (không chết), việc là REVISE_RESULTS (không chạy lại bộ lọc
    cũ), và `COMPACT_SIZE` vào điểm (danh sách mới thực sự nhỏ hơn).
    """

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(intents=[])),
        Uow(
            Pending([]),
            Sessions(
                [],
                {
                    SlotName.VEHICLE_TYPE: VehicleType.CAR.value,
                    SlotName.BUDGET_MAX_VND: 800_000_000,
                    SlotName.PURPOSE: "đưa gia đình đi lại",
                },
            ),
        ),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="nếu anh muốn 1 chiếc nhỏ hơn thì sao",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": ["v-vf8", "v-vf7"]},
            "revision": 1,
            "updated_at": "2026-08-26T00:00:00+00:00",
        },
    )

    assert Intent.ADVISORY in result.intents
    assert result.task_action is TaskAction.REVISE_RESULTS
    assert result.excluded_vehicle_ids == ("v-vf8", "v-vf7")
    assert "COMPACT_SIZE" in result.feature_mentions


@pytest.mark.asyncio
async def test_a_cheaper_request_revises_without_inventing_a_feature_need() -> None:
    """Rẻ hơn là chuyện của giá — không được gán thêm một mã trang bị nào."""

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(intents=[])),
        Uow(
            Pending([]),
            Sessions([], {SlotName.VEHICLE_TYPE: VehicleType.CAR.value, SlotName.BUDGET_MAX_VND: 800_000_000}),
        ),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="có mẫu nào rẻ hơn không em",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": ["v-vf8"]},
            "revision": 1,
            "updated_at": "2026-08-26T00:00:00+00:00",
        },
    )

    assert result.task_action is TaskAction.REVISE_RESULTS
    assert result.feature_mentions == []


@pytest.mark.asyncio
async def test_a_first_turn_need_statement_is_not_read_as_a_revision() -> None:
    """Chưa có hồ sơ nào thì "nhỏ gọn" là lời khai nhu cầu, không phải đổi kết quả."""

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(intents=[Intent.ADVISORY], budget_max_vnd="500 triệu")),
        Uow(Pending([])),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="anh có 500 triệu và muốn xe nhỏ gọn đi trong nội thành",
    )

    assert result.task_action is not TaskAction.REVISE_RESULTS
    assert result.excluded_vehicle_ids == ()


@pytest.mark.asyncio
async def test_asking_to_book_is_never_read_as_a_vague_advice_request() -> None:
    """BUG PROD 2026-08-27, đọc từ log Sếp dán.

    Khách đã xem xe, đã xem chi phí, rồi gõ *"cho anh đặt lịch"* — và nhận về
    *"cho em biết ngân sách hoặc số chỗ ngồi mong muốn"*: hỏi lại ngân sách họ đã
    nói (500 triệu), và hỏi số chỗ vốn đã bỏ không hỏi.

    Cùng họ với lỗi tỉnh+km: mô hình trích rỗng nên `_has_new_task_information`
    trả False và lượt rơi xuống `CLARIFY_TASK`. Xin lái thử KHÔNG phải một lượt
    "muốn tư vấn" mơ hồ — đó là bước cuối của chính cuộc tư vấn vừa xong.
    """

    service = SlotExtractionServiceImpl(
        FakeLLM(LLMExtractionPayload(intents=[Intent.ADVISORY])),
        Uow(Pending([]), Sessions([], {SlotName.BUDGET_MAX_VND: 500_000_000})),
    )

    result = await service.extract(
        session_id="s",
        customer_id="customer",
        vehicle_type=VehicleType.CAR,
        user_message="cho anh đặt lịch",
        active_task={
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": "2026-08-27T00:00:00+00:00",
        },
    )

    assert result.task_action is not TaskAction.CLARIFY_TASK
