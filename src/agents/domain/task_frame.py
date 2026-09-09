"""Khung việc theo intent: intent này CẦN gì, thiếu thì HỎI câu nào, bị chen ngang thì TREO rồi quay lại.

Bối cảnh (Sếp 2026-08-29): "vào một intent mà thiếu thông tin thì đi tiếp vào
đâu, hỏi gì để intent đó hoạt động — nó không làm được". Cuộc tư vấn có cây slot
(`slot_planning`) nên tự hỏi tiếp được; còn các việc công cụ (lái thử, giá lăn
bánh, so sánh, tìm địa điểm) mỗi việc tự viết tay một bản ghi chờ trong `chain`
và `route_intent`, không có hợp đồng chung. Hệ quả đo được:

- Bản ghi chờ bị THẢ khi khách hỏi chen một câu khác (`release_on_failure`,
  `dropped_notice`, `SWITCH_TASK`), trả lời xong không ai quay lại việc dở.
- Câu hỏi lại mặc định là "cho em xin lại thông tin test_drive_vehicle" — tên
  slot kỹ thuật lọt ra màn chat.
- Có xe khách đang xem (`interest_vehicle`) mà việc treo vẫn hỏi "mẫu nào".

Module này KHÔNG thay các nhánh đang chạy: nó là bảng khai báo dùng chung để
(1) đặt câu hỏi đúng lời cho mọi slot công cụ, (2) điền sẵn từ ngữ cảnh khi quay
lại, (3) treo/khôi phục một việc bị chen ngang. Mỗi phiên chỉ có MỘT cột
`pending_slot_request` (JSONB), nên việc bị treo nằm chung cột đó dưới khoá
`suspended` — `PendingSlotRequest.from_payload` bỏ qua khoá lạ, nên dữ liệu cũ
và code cũ đọc cột này không đổi hành vi.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final

from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.values import NEARBY_LOCATION_INTENTS, Intent, SlotName

#: Khoá trong cột `pending_slot_request` giữ việc đang bị treo.
SUSPENDED_KEY: Final[str] = "suspended"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Một trường bắt buộc của việc: tên slot, câu hỏi khi thiếu, và slot ngữ cảnh điền sẵn được."""

    name: str
    question: str
    #: Khoá trong `conversation_slots` có thể điền sẵn trường này mà không cần hỏi.
    context_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskFrame:
    """Hợp đồng "intent này cần gì" — đủ để hỏi tiếp mà không cần LLM."""

    intent: str
    #: Tên việc bằng lời khách, dùng khi quay lại: "Quay lại lịch lái thử VF 5: …".
    label: str
    fields: tuple[FieldSpec, ...]
    #: Khoá trong `partial_form` mang tên xe của việc (để xưng đúng khi quay lại).
    subject_keys: tuple[str, ...] = ()

    def field(self, name: str) -> FieldSpec | None:
        for spec in self.fields:
            if spec.name == name:
                return spec
        return None

    def question_for(self, slot_name: str) -> str | None:
        spec = self.field(slot_name)
        return None if spec is None else spec.question

    def prefill(self, form: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
        """Điền các trường còn trống từ ngữ cảnh phiên. Không ghi đè giá trị đã có."""

        filled = dict(form)
        for spec in self.fields:
            if _present(filled.get(spec.name)):
                continue
            for key in spec.context_keys:
                value = context.get(key)
                if _present(value):
                    filled[spec.name] = value
                    break
        return filled

    def missing(self, form: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.fields if not _present(form.get(spec.name)))

    def subject(self, form: Mapping[str, Any]) -> str:
        for key in self.subject_keys:
            value = form.get(key)
            if isinstance(value, list | tuple):
                names = [str(item) for item in value if _present(item)]
                if names:
                    return " và ".join(names)
            elif _present(value):
                return str(value)
        return ""


def _present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value != "__declined__"
    if isinstance(value, list | tuple | dict):
        return len(value) > 0
    return True


_VEHICLE_CONTEXT: Final[tuple[str, ...]] = (SlotName.INTEREST_VEHICLE.value,)

TASK_FRAMES: Final[Mapping[str, TaskFrame]] = {
    # Giá lăn bánh: bước hỏi mẫu (intent riêng) rồi bước hỏi tỉnh.
    "ON_ROAD_VEHICLE": TaskFrame(
        intent="ON_ROAD_VEHICLE",
        label="giá lăn bánh",
        fields=(
            FieldSpec(
                "on_road_vehicle",
                "Anh/chị muốn tính giá lăn bánh cho mẫu xe nào ạ?",
                context_keys=_VEHICLE_CONTEXT,
            ),
        ),
        subject_keys=("on_road_vehicle",),
    ),
    "ON_ROAD_PRICE_LOOKUP": TaskFrame(
        intent="ON_ROAD_PRICE_LOOKUP",
        label="giá lăn bánh",
        fields=(
            FieldSpec("vehicle_variant", "Anh/chị muốn tính giá lăn bánh cho mẫu xe nào ạ?"),
            FieldSpec(
                "province",
                "Anh/chị dự định đăng ký xe ở tỉnh/thành nào ạ?",
                context_keys=(SlotName.REGISTRATION_PROVINCE.value,),
            ),
        ),
        subject_keys=("vehicle_name",),
    ),
    "TEST_DRIVE": TaskFrame(
        intent="TEST_DRIVE",
        label="lịch lái thử",
        fields=(
            FieldSpec(
                "test_drive_vehicle",
                "Anh/chị muốn lái thử mẫu xe nào ạ?",
                context_keys=_VEHICLE_CONTEXT,
            ),
            FieldSpec(
                "user_location",
                "Anh/chị đang ở khu vực nào để em tìm showroom gần nhất ạ?",
            ),
        ),
        subject_keys=("test_drive_vehicle", "vehicle_name"),
    ),
    Intent.COMPARE_VEHICLES.value: TaskFrame(
        intent=Intent.COMPARE_VEHICLES.value,
        label="so sánh xe",
        fields=(FieldSpec("compare_targets", "Anh/chị muốn so sánh những mẫu xe nào ạ?"),),
        subject_keys=("resolved_vehicle_names",),
    ),
    **{
        name: TaskFrame(
            intent=name,
            label="tìm địa điểm",
            fields=(
                FieldSpec("location_kind", "Anh/chị muốn tìm showroom hay trạm sạc ạ?"),
                FieldSpec("user_location", "Anh/chị đang ở khu vực nào để em tìm gần nhất ạ?"),
            ),
        )
        for name in NEARBY_LOCATION_INTENTS
    },
}


def frame_for(intent: object) -> TaskFrame | None:
    return TASK_FRAMES.get(intent) if isinstance(intent, str) else None


def question_for(intent: object, slot_name: str) -> str | None:
    """Câu hỏi đúng lời cho một slot công cụ; `None` nếu intent/slot không khai báo."""

    frame = frame_for(intent)
    return None if frame is None else frame.question_for(slot_name)


def is_suspendable(pending: PendingSlotRequest | None) -> bool:
    """Việc công cụ thì treo được; slot của cây tư vấn thì luồng chủ tự hỏi lại."""

    return pending is not None and frame_for(pending.intent) is not None


def suspended_from_payload(payload: Mapping[str, Any] | None) -> PendingSlotRequest | None:
    if not isinstance(payload, Mapping):
        return None
    return PendingSlotRequest.from_payload(payload.get(SUSPENDED_KEY))


def with_suspended(
    pending_payload: Mapping[str, Any] | None, suspended: PendingSlotRequest | None
) -> dict[str, Any] | None:
    """Gộp việc treo vào payload cột. Không có gì để ghi → `None` (xoá cột)."""

    base = {k: v for k, v in dict(pending_payload or {}).items() if k != SUSPENDED_KEY}
    if suspended is not None:
        base[SUSPENDED_KEY] = suspended.to_payload()
    return base or None


@dataclass(frozen=True, slots=True)
class ResumePlan:
    """Cách quay lại một việc treo sau khi câu chen ngang đã được trả lời."""

    #: Bản ghi chờ mới (đã điền sẵn từ ngữ cảnh). `None` khi việc đã đủ để chạy.
    pending: PendingSlotRequest | None
    #: Form đã điền sẵn — dùng chạy thẳng tool khi không còn thiếu gì.
    form: dict[str, Any]
    #: Câu nói với khách khi quay lại; rỗng khi việc chạy thẳng.
    prompt: str
    label: str


def plan_resume(suspended: PendingSlotRequest, context: Mapping[str, Any], now: datetime) -> ResumePlan | None:
    """Điền sẵn từ ngữ cảnh rồi quyết định: hỏi tiếp trường nào, hay chạy luôn."""

    frame = frame_for(suspended.intent)
    if frame is None:
        return None
    form = frame.prefill({k: v for k, v in dict(suspended.partial_form).items() if k != "pending_group"}, context)
    missing = frame.missing(form)
    subject = frame.subject(form)
    label = f"{frame.label} {subject}".strip()
    if not missing:
        return ResumePlan(pending=None, form=form, prompt="", label=label)
    next_slot = missing[0] if suspended.missing_slot not in missing else suspended.missing_slot
    question = frame.question_for(next_slot) or "anh/chị cho em xin thêm thông tin giúp ạ?"
    pending = replace(suspended, missing_slot=next_slot, partial_form=form, asked_at=now, turn_count=0)
    return ResumePlan(pending=pending, form=form, prompt=f"Quay lại {label} lúc nãy: {question}", label=label)


__all__ = [
    "SUSPENDED_KEY",
    "TASK_FRAMES",
    "FieldSpec",
    "ResumePlan",
    "TaskFrame",
    "frame_for",
    "is_suspendable",
    "plan_resume",
    "question_for",
    "suspended_from_payload",
    "with_suspended",
]
