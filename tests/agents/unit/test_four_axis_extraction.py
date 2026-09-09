"""Bốn trục đi trọn từ payload của mô hình tới `ExtractedSlots`.

Điều kiện then chốt: MỌI trục đều có mặc định an toàn. Mô hình chưa biết trả
chúng — hoặc trả rác — thì lượt vẫn chạy đúng như trước. Đó là điều làm cho việc
chuyển đổi này làm dần được, thay vì phải sửa mọi consumer trong một PR.
"""

from __future__ import annotations

import pytest

from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.values import (
    DialogueAct,
    Intent,
    IntentType,
    Severity,
    Topic,
    VehicleType,
)
from src.agents.services.slot_extraction import SlotExtractionServiceImpl

# Dùng lại fake của bộ test trích slot sẵn có thay vì tự dựng: hình dạng
# transaction đã đúng ở đó, và hai bản fake lệch nhau là mầm bug thầm lặng.
from tests.agents.unit.test_slot_extraction import FakeLLM, Pending, Uow  # noqa: E402


async def _extract(payload: LLMExtractionPayload, message: str = "cau hoi"):
    llm = FakeLLM(payload)
    service = SlotExtractionServiceImpl(llm, Uow(Pending([])))
    result = await service.extract(
        session_id="s", customer_id="khach", vehicle_type=None, user_message=message
    )
    return result, llm


@pytest.mark.asyncio
async def test_a_complaint_that_asks_a_price_question_keeps_both_axes() -> None:
    """Ca thúc đẩy cả Todo 6: "Đắt quá, VF 8 giá bao nhiêu?"."""

    result, llm = await _extract(
        LLMExtractionPayload(
            dialogue_act=DialogueAct.COMPLAIN,
            task=IntentType.PRICE_TCO_QUERY,
            primary_topic=Topic.PRICE_TCO,
            intents=[Intent.CATALOG_LOOKUP],
        )
    )
    assert result.dialogue_act is DialogueAct.COMPLAIN
    assert result.task is IntentType.PRICE_TCO_QUERY
    assert llm.payload is not None, "van chi MOT lan goi trich xuat"


@pytest.mark.asyncio
async def test_a_calm_report_of_smoke_keeps_severity_separate_from_act() -> None:
    result, _ = await _extract(
        LLMExtractionPayload(
            dialogue_act=DialogueAct.REQUEST,
            severity=Severity.CRITICAL,
            primary_topic=Topic.CUSTOMER_EXPERIENCE,
        )
    )
    assert result.dialogue_act is DialogueAct.REQUEST
    assert result.severity is Severity.CRITICAL


@pytest.mark.asyncio
async def test_secondary_topics_drop_the_primary_and_keep_order() -> None:
    result, _ = await _extract(
        LLMExtractionPayload(
            primary_topic=Topic.VEHICLE,
            secondary_topics=["VEHICLE", "POLICY", "PRICE_TCO", "POLICY"],
        )
    )
    assert result.primary_topic is Topic.VEHICLE
    assert result.secondary_topics == (Topic.POLICY, Topic.PRICE_TCO)


@pytest.mark.asyncio
async def test_a_payload_without_any_axis_falls_back_safely() -> None:
    """Mô hình cũ chưa biết bốn trục — lượt vẫn phải chạy y như trước."""

    result, _ = await _extract(LLMExtractionPayload(intents=[Intent.ADVISORY]))
    assert result.task is None, "None nghia la 'chua noi', khong duoc doan"
    assert result.primary_topic is Topic.OTHER
    assert result.secondary_topics == ()
    assert result.severity is Severity.NORMAL
    assert result.human_requested is False
    assert result.intents == [Intent.ADVISORY], "nhan cu van la duong chay chinh"


@pytest.mark.asyncio
async def test_a_malformed_secondary_topic_never_breaks_the_turn() -> None:
    result, _ = await _extract(
        LLMExtractionPayload(
            primary_topic=Topic.VEHICLE, secondary_topics=["KHONG_CO_THAT", "POLICY"]
        )
    )
    assert Topic.POLICY in result.secondary_topics
    assert all(isinstance(item, Topic) for item in result.secondary_topics)


@pytest.mark.asyncio
async def test_the_model_can_flag_a_human_request_as_a_soft_signal() -> None:
    """Tín hiệu MỀM: hợp với sàn keyword ở `domain/escalation`, không thay thế."""

    result, _ = await _extract(LLMExtractionPayload(human_requested=True))
    assert result.human_requested is True


@pytest.mark.asyncio
async def test_the_public_extraction_contract_still_carries_the_old_fields() -> None:
    """Thêm trục KHÔNG được làm mất field cũ — consumer hiện hữu đọc chúng."""

    # Tên xe phải khớp câu của CHÍNH lượt này (luật chống mô hình bịa tên), nên
    # câu đầu vào phải nhắc "VF 8" thật.
    result, _ = await _extract(
        LLMExtractionPayload(
            vehicle_type=VehicleType.CAR,
            intents=[Intent.ADVISORY],
            vehicle_name_mentions=["VF 8"],
        ),
        message="VF 8 giá bao nhiêu",
    )
    assert result.intents, "nhan cu phai con nguyen"
    assert result.vehicle_name_mentions == ["VF 8"]
