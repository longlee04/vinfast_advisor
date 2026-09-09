"""[Prompt mục 3.2] Cá nhân hoá câu hỏi slot dựa trên thông tin đã biết.

Bước này LUÔN optional: nó chỉ làm câu hỏi tự nhiên hơn, không mang thông tin
nào mà luồng hội thoại phụ thuộc. Vì vậy mọi lỗi ở đây đều nuốt và rơi về câu
template — để một lời chào mượt hơn làm hỏng cả lượt tư vấn là đánh đổi sai.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.agents.domain.inquiry_form import VehicleInquiryForm
from src.agents.domain.values import SlotName
from src.agents.logging import get_agent_logger
from src.agents.prompts.question_variants import get_question_variant

logger = get_agent_logger("agent.services.question_generation")

# [GIẢ ĐỊNH] Chỉ cá nhân hoá các slot thực sự có ngữ cảnh liên quan để nhắc tới.
# Bật tràn lan sẽ cộng một LLM call vào gần như mọi lượt, đúng thứ prompt cảnh
# báo về timeout hosting.
_PERSONALIZABLE: frozenset[SlotName] = frozenset({SlotName.BUDGET_MAX_VND, SlotName.PURPOSE, SlotName.HABIT_NEED_TAGS})

# Ngữ cảnh nào đáng nhắc khi hỏi slot nào.
_CONTEXT_FOR: Mapping[SlotName, tuple[str, ...]] = {
    SlotName.BUDGET_MAX_VND: ("vehicle_type", "passenger_count"),
    SlotName.PURPOSE: ("vehicle_type", "passenger_count"),
    SlotName.HABIT_NEED_TAGS: ("vehicle_type", "purpose"),
}


class QuestionPersonalizerPort(Protocol):
    """Viết lại một câu hỏi cho tự nhiên hơn dựa trên form đã biết."""

    async def personalize(self, *, slot_name: str, form_summary: str, base_question: str) -> str | None: ...


def has_useful_context(form: VehicleInquiryForm, slot: SlotName) -> bool:
    """Có ít nhất một field liên quan đã biết thì mới đáng cá nhân hoá."""

    if slot not in _PERSONALIZABLE:
        return False
    return any(getattr(form, name, None) is not None for name in _CONTEXT_FOR.get(slot, ()))


def summarize_form(form: VehicleInquiryForm) -> str:
    """Tóm tắt form thành một dòng để nhét vào prompt cá nhân hoá."""

    parts = [f"{name}={value}" for name, value in form.to_slots().items() if value is not None]
    return ", ".join(parts)


async def generate_question_for_field(
    *,
    slot: SlotName,
    form: VehicleInquiryForm,
    retry_count: int = 0,
    personalizer: QuestionPersonalizerPort | None = None,
) -> str:
    """Câu hỏi cuối cùng gửi khách: template biến thể, cá nhân hoá nếu được."""

    base_question = get_question_variant(slot, retry_count)
    if personalizer is None or not has_useful_context(form, slot):
        return base_question
    try:
        personalized = await personalizer.personalize(
            slot_name=slot.value,
            form_summary=summarize_form(form),
            base_question=base_question,
        )
    except Exception:  # noqa: BLE001 - xem docstring module
        logger.warning("ca nhan hoa cau hoi loi, dung template", exc_info=True)
        return base_question
    if isinstance(personalized, str) and personalized.strip():
        return personalized.strip()
    return base_question
