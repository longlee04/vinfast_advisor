"""Extraction uses the pending slot context and closes unanswered slots."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest

from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.slot_policy import next_slot
from src.agents.domain.values import Intent, SlotName, VehicleType
from src.agents.services.slot_extraction import SlotExtractionServiceImpl


class RecordingLLM:
    def __init__(self, payload: LLMExtractionPayload) -> None:
        self.payload = payload
        self.last_kwargs: dict[str, object] = {}

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
        self.last_kwargs = kwargs
        return self.payload


@dataclass
class Pending:
    values: list[str] = field(default_factory=list)

    async def record(self, session_id: str, customer_id: str, mentions: list[str]) -> None:
        self.values.extend(mentions)

    async def consume(self, session_id: str, customer_id: str) -> list[str]:
        values = list(self.values)
        self.values.clear()
        return values


@dataclass
class Sessions:
    upserts: dict[SlotName, object]

    async def ensure_session(self, session_id: str, customer_id: str, hint: object) -> None:
        return None

    async def get_slots(self, session_id: str, customer_id: str) -> dict[SlotName, object]:
        return dict(self.upserts)

    async def upsert_slot(self, session_id: str, slot_name: SlotName, value: object) -> None:
        self.upserts[slot_name] = value


@dataclass
class Transaction:
    pending_mentions: Pending
    sessions: Sessions


class Uow:
    def __init__(self, known: dict[SlotName, object]) -> None:
        self.transaction_value = Transaction(Pending(), Sessions(dict(known)))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        yield self.transaction_value


CAR_THROUGH_BUDGET = {
    SlotName.VEHICLE_TYPE: VehicleType.CAR.value,
    SlotName.PASSENGER_COUNT: 5,
    SlotName.BUDGET_MAX_VND: 700_000_000,
}


@pytest.mark.asyncio
async def test_price_first_complete_state_does_not_prompt_for_optional_purpose() -> None:
    llm = RecordingLLM(LLMExtractionPayload(intents=[Intent.ADVISORY]))
    service = SlotExtractionServiceImpl(llm, Uow(CAR_THROUGH_BUDGET))

    await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=VehicleType.CAR.value,
        user_message="Chủ yếu đi làm hằng ngày",
    )

    assert llm.last_kwargs["conversation_history"] == ""


@pytest.mark.asyncio
async def test_working_memory_is_forwarded_and_pending_slot_context_is_appended() -> None:
    llm = RecordingLLM(LLMExtractionPayload(intents=[Intent.CATALOG_LOOKUP]))
    service = SlotExtractionServiceImpl(llm, Uow({SlotName.VEHICLE_TYPE: VehicleType.CAR.value}))

    await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=VehicleType.CAR.value,
        user_message="Mẫu còn lại giá bao nhiêu?",
        conversation_history="Đã loại VF 5; mẫu còn lại là VF 7.",
    )

    history = str(llm.last_kwargs["conversation_history"])
    assert "Đã loại VF 5; mẫu còn lại là VF 7." in history
    assert "budget_max_vnd" in history


@pytest.mark.asyncio
async def test_optional_purpose_is_not_invented_when_llm_omits_it() -> None:
    llm = RecordingLLM(LLMExtractionPayload(intents=[Intent.ADVISORY]))
    service = SlotExtractionServiceImpl(llm, Uow(CAR_THROUGH_BUDGET))

    result = await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=VehicleType.CAR.value,
        user_message="Chủ yếu đưa con đi học hằng ngày",
    )

    assert SlotName.PURPOSE not in result.slots


@pytest.mark.asyncio
async def test_evasive_answer_does_not_create_an_optional_purpose_slot() -> None:
    service = SlotExtractionServiceImpl(
        RecordingLLM(LLMExtractionPayload(intents=[Intent.ADVISORY])),
        Uow(CAR_THROUGH_BUDGET),
    )

    result = await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=VehicleType.CAR.value,
        user_message="chưa biết nữa em",
    )

    assert SlotName.PURPOSE not in result.slots


@pytest.mark.asyncio
async def test_optional_habit_is_not_asked_or_filled_after_price_first_completion() -> None:
    known = {**CAR_THROUGH_BUDGET, SlotName.PURPOSE: "đi làm"}
    service = SlotExtractionServiceImpl(RecordingLLM(LLMExtractionPayload(intents=[Intent.ADVISORY])), Uow(known))

    result = await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=VehicleType.CAR.value,
        user_message="dạ để em nghĩ thêm rồi báo lại anh nhé",
    )

    assert SlotName.HABIT_NEED_TAGS not in result.slots


@pytest.mark.asyncio
async def test_catalog_question_is_never_salvaged_into_pending_purpose() -> None:
    service = SlotExtractionServiceImpl(
        RecordingLLM(LLMExtractionPayload(vehicle_name_mentions=["VF 5"], intents=[Intent.CATALOG_LOOKUP])),
        Uow(CAR_THROUGH_BUDGET),
    )

    result = await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=VehicleType.CAR.value,
        user_message="VF 5 giá bao nhiêu ạ?",
    )

    assert SlotName.PURPOSE not in result.slots


@pytest.mark.asyncio
async def test_short_vehicle_reply_keeps_budget_and_advisory_session_context() -> None:
    known = {SlotName.BUDGET_MAX_VND: 500_000_000}
    uow = Uow(known)
    service = SlotExtractionServiceImpl(
        RecordingLLM(LLMExtractionPayload(vehicle_type=VehicleType.CAR)),
        uow,
    )

    result = await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=None,
        user_message="ô tô nhé",
    )

    assert result.intents == [Intent.ADVISORY]
    assert result.slots[SlotName.VEHICLE_TYPE] == VehicleType.CAR.value
    assert uow.transaction_value.sessions.upserts[SlotName.BUDGET_MAX_VND] == 500_000_000


@pytest.mark.asyncio
async def test_explicit_budget_is_recovered_when_llm_omits_slots_and_intent() -> None:
    service = SlotExtractionServiceImpl(
        RecordingLLM(LLMExtractionPayload()),
        Uow({}),
    )

    result = await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=None,
        user_message="ô tô khoảng 500 triệu",
    )

    # "khoảng 500 triệu" là một ƯỚC LƯỢNG, nên nó điền cả sàn lẫn trần — nhưng
    # nới CHỈ XUỐNG DƯỚI (Sếp 2026-08-26: "nếu người dùng cung cấp tài chính thì
    # đề xuất không được vượt quá tài chính"). Trần đúng bằng con số khách nói.
    assert result.slots == {
        SlotName.VEHICLE_TYPE: VehicleType.CAR.value,
        SlotName.BUDGET_MIN_VND: 400_000_000,
        SlotName.BUDGET_MAX_VND: 500_000_000,
        SlotName.BUDGET_STATED_VND: 500_000_000,
    }
    assert result.intents == [Intent.ADVISORY]


@pytest.mark.asyncio
async def test_explicit_branch_switch_reuses_previous_budget_without_cue_words() -> None:
    known = {
        SlotName.VEHICLE_TYPE: VehicleType.CAR.value,
        SlotName.BUDGET_MAX_VND: 500_000_000,
    }
    uow = Uow(known)
    service = SlotExtractionServiceImpl(
        RecordingLLM(LLMExtractionPayload(vehicle_type=VehicleType.ELECTRIC_MOTORBIKE)),
        uow,
    )

    result = await service.extract(
        session_id="s",
        customer_id="c",
        vehicle_type=VehicleType.CAR.value,
        user_message="xe máy điện cơ",
    )

    merged = {**known, **result.slots}
    assert result.intents == [Intent.ADVISORY]
    assert merged[SlotName.BUDGET_MAX_VND] == 500_000_000
    assert merged[SlotName.VEHICLE_TYPE] == VehicleType.ELECTRIC_MOTORBIKE.value
    assert next_slot(VehicleType.ELECTRIC_MOTORBIKE, merged) is None


@pytest.mark.parametrize(
    ("message", "proposed", "expected"),
    [
        # BUG THẬT trên prod 2026-08-27: mô hình đọc "xe điện" thành xe máy điện,
        # rồi khách nói 700 triệu, gia đình 5 người mà vẫn nhận về xe máy.
        ("tôi muốn tư vấn mua xe điện", VehicleType.ELECTRIC_MOTORBIKE, None),
        ("mua xe điện với", VehicleType.CAR, None),
        # Câu CÓ nêu nhánh thì lời đoán không còn là đoán.
        ("tôi muốn mua ô tô điện", VehicleType.CAR, VehicleType.CAR),
        ("tư vấn xe máy điện giúp anh", VehicleType.ELECTRIC_MOTORBIKE, VehicleType.ELECTRIC_MOTORBIKE),
    ],
)
def test_unfounded_vehicle_type_guess_is_dropped_so_the_bot_asks(
    message: str, proposed: VehicleType, expected: VehicleType | None
) -> None:
    from src.agents.services.slot_extraction import _slots_from_payload

    slots, _ = _slots_from_payload(
        LLMExtractionPayload(vehicle_type=proposed, intents=[Intent.ADVISORY]),
        message,
        current_vehicle_type=None,
    )

    assert slots.get(SlotName.VEHICLE_TYPE) == (expected.value if expected is not None else None)


def test_structured_seat_evidence_still_picks_the_car_branch() -> None:
    """"Phân vân giữa xe 5 chỗ và 7 chỗ" chọn nhánh ô tô dù không có chữ "ô tô"."""

    from src.agents.services.slot_extraction import _slots_from_payload

    slots, _ = _slots_from_payload(
        LLMExtractionPayload(vehicle_type=VehicleType.CAR, passenger_count=5, intents=[Intent.ADVISORY]),
        "Tôi đang phân vân giữa xe 5 chỗ và 7 chỗ",
        current_vehicle_type=None,
    )

    assert slots.get(SlotName.VEHICLE_TYPE) == VehicleType.CAR.value
