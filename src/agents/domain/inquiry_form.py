"""Schema tổng hợp cho toàn bộ form tư vấn xe — thuần, không I/O.

Đây là VIEW có kiểu trên `dict[SlotName, SlotValue]` đang lưu ở
`conversation_slots`, không phải kho lưu trữ mới.

[GIẢ ĐỊNH] Không thay `dict[SlotName, SlotValue]` bằng model này ở tầng lưu trữ.
Prompt yêu cầu "giữ đúng tên field cũ để không phá vỡ phần downstream", mà
`slot_mapping.to_filter_criteria`, `recommendation`, `slot_policy` và toàn bộ
repository đều đọc dict đó. Đổi kho lưu trữ sẽ phá cả chuỗi Lớp 1 → score → TCO
mà không đổi lấy hành vi nào cho khách. `from_slots`/`to_slots` là hai đầu cầu.

[GIẢ ĐỊNH] Kiểu bọc tên là `SlotAnswer`, không phải `SlotValue` như prompt viết:
`SlotValue` đã là union nguyên thuỷ trong `domain/values.py` và bị hàng chục
module import. Trùng tên sẽ gây nhầm lẫn im lặng ở chỗ nguy hiểm nhất.

[GIẢ ĐỊNH] `vehicle_type` giữ `VehicleType` (CAR / ELECTRIC_MOTORBIKE) thay vì
`Literal["gasoline","electric","hybrid"]` như prompt gợi ý: catalog chỉ có xe
điện, không có bản xăng/hybrid nào để map sang.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.agents.domain.budget_parsing import NO_BUDGET_LIMIT_VND
from src.agents.domain.slot_policy import next_slot
from src.agents.domain.values import (
    DECLINED_SLOT_VALUE,
    SlotName,
    SlotValue,
    VehicleType,
    is_declined,
)

AnswerKind = Literal["exact", "range", "open", "unknown"]

# Slot mang văn bản tự do: bọc `SlotAnswer` cho chúng không thêm thông tin gì,
# `kind` luôn là "exact" hoặc "unknown" (prompt mục 1, ghi chú [GIẢ ĐỊNH]).
# `PURPOSE_BUCKET` cũng đi theo nhánh này dù giá trị là enum đóng, không phải
# free text: nó không bao giờ được hỏi trực tiếp nên không cần `SlotAnswer`
# (kind exact/range/open) — chỉ cần đọc/ghi nguyên văn như `purpose`.
_FREE_TEXT_SLOTS = frozenset(
    {
        SlotName.PURPOSE,
        SlotName.PURPOSE_BUCKET,
        SlotName.HABIT_NEED_TAGS,
        # Mã tỉnh là một chuỗi khách nói ra, không phải câu trả lời có/không hay
        # một con số — nó không mang trạng thái "đã từ chối" nào để `SlotAnswer`
        # phải theo dõi.
        SlotName.REGISTRATION_PROVINCE,
    }
)


class SlotAnswer(BaseModel):
    """Một giá trị slot kèm việc khách đã trả lời theo kiểu nào."""

    model_config = ConfigDict(frozen=True)

    kind: AnswerKind
    value: Any | None = None
    min_value: Any | None = None
    max_value: Any | None = None
    raw_text: str = ""

    @property
    def is_answered(self) -> bool:
        """`open` tính là ĐÃ trả lời: khách đã nói, chỉ là không đặt giới hạn."""

        return self.kind in {"exact", "range", "open"}


def answer_from_slot(slot: SlotName, value: SlotValue) -> SlotAnswer:
    """Đọc giá trị đang lưu thành `SlotAnswer`, giữ nguyên ngữ nghĩa sentinel."""

    if value is None:
        return SlotAnswer(kind="unknown")
    if is_declined(value):
        return SlotAnswer(kind="open", raw_text=DECLINED_SLOT_VALUE)
    if slot is SlotName.BUDGET_MAX_VND and _as_number(value) == NO_BUDGET_LIMIT_VND:
        return SlotAnswer(kind="open", value=value, raw_text=str(value))
    return SlotAnswer(kind="exact", value=value, raw_text=str(value))


def _as_number(value: SlotValue) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class VehicleInquiryForm(BaseModel):
    """Toàn bộ field của form tư vấn, gộp từ cây slot A3-1."""

    model_config = ConfigDict(frozen=True)

    vehicle_type: VehicleType | None = None
    passenger_count: SlotAnswer | None = None
    required_range_km: SlotAnswer | None = None
    home_charging: SlotAnswer | None = None
    budget_max_vnd: SlotAnswer | None = None
    #: Sàn ngân sách, chỉ có mặt khi khách nói một KHOẢNG ("từ 300 đến 700 triệu")
    #: hoặc một sàn ("trên 500 triệu"). `None` là ca thường gặp nhất.
    budget_min_vnd: SlotAnswer | None = None
    #: Con số khách nói ra khi họ nói "khoảng X" — xem `SlotName.BUDGET_STATED_VND`.
    budget_stated_vnd: SlotAnswer | None = None
    purpose: str | None = None
    purpose_bucket: str | None = None
    #: Mẫu khách vừa xem/hỏi riêng — bối cảnh, không phải tiêu chí lọc.
    interest_vehicle: str | None = None
    max_load_kg: SlotAnswer | None = None
    habit_need_tags: list[str] | str | None = None
    #: Mã tỉnh nơi khách ĐĂNG KÝ xe — quyết định lệ phí biển số trong bảng chi
    #: phí. Không bao giờ được hỏi thành một mục: suy từ vị trí trình duyệt, và
    #: khách sửa được bất kỳ lúc nào. Xem `SlotName.REGISTRATION_PROVINCE`.
    registration_province: str | None = None

    @classmethod
    def from_slots(cls, slots: Mapping[str, SlotValue]) -> VehicleInquiryForm:
        """Dựng form từ dict slot đang lưu; khoá lạ bị bỏ qua, không raise."""

        fields: dict[str, Any] = {}
        for raw_name, value in slots.items():
            try:
                slot = SlotName(raw_name)
            except ValueError:
                continue
            if slot is SlotName.VEHICLE_TYPE:
                fields[slot.value] = _coerce_vehicle_type(value)
            elif slot in _FREE_TEXT_SLOTS:
                fields[slot.value] = value
            else:
                fields[slot.value] = answer_from_slot(slot, value)
        return cls(**fields)

    def to_slots(self) -> dict[str, SlotValue]:
        """Trả về đúng hình dạng dict mà repository và Lớp 1 đang đọc."""

        slots: dict[str, SlotValue] = {}
        for slot in SlotName:
            field = getattr(self, slot.value)
            if field is None:
                continue
            if slot is SlotName.VEHICLE_TYPE:
                slots[slot.value] = field.value if isinstance(field, VehicleType) else field
            elif isinstance(field, SlotAnswer):
                slots[slot.value] = (
                    field.value if field.kind != "open" or field.value is not None else DECLINED_SLOT_VALUE
                )
            else:
                slots[slot.value] = field
        return slots

    def merge(self, updates: VehicleInquiryForm) -> VehicleInquiryForm:
        """Ghép field mới vào form cũ.

        Chỉ ghi đè khi field mới thực sự mang thông tin: `None` và `unknown` là
        "lượt này khách không nói gì về field đó", không phải "khách xoá nó".
        Thiếu luật này thì mỗi lượt trả lời một field sẽ xoá sạch các field trước.
        """

        merged = self.model_dump()
        for name, value in updates.model_dump().items():
            if value is None:
                continue
            if isinstance(value, dict) and value.get("kind") == "unknown":
                continue
            merged[name] = value
        return VehicleInquiryForm(**merged)


class FormState(BaseModel):
    """[A7-5] Toàn bộ state một phiên cần để xử lý lượt kế tiếp.

    Là VIEW gom ba thứ ĐÃ CÓ SẴN, không phải kho lưu trữ mới: `form` là
    `conversation_slots`, `retry_count` là `slot_ask_attempts`, còn hai field
    quote là hai cột mới trên `conversation_sessions`.

    Có mặt `last_quote_evaluation` để một lượt xác nhận ("ok xe có vẻ được đấy")
    không phải dựng lại đánh giá từ con số không. Dựng lại từ một lượt không mang
    thông tin nào thì mọi cờ đều `None`, và `None` theo default-deny là RỦI RO —
    tức lời khen của khách bị đẩy sang tư vấn viên duyệt.

    [GIẢ ĐỊNH] Chỉ giữ đánh giá của báo giá GẦN NHẤT, không giữ lịch sử mọi báo
    giá trong phiên: đủ để một lượt xác nhận biết nó đang xác nhận cái gì, và
    tránh phình state cho thứ chưa ai đọc tới.
    """

    model_config = ConfigDict(frozen=True)

    form: VehicleInquiryForm = VehicleInquiryForm()
    retry_count: dict[str, int] = {}
    # Giữ dạng dict thô thay vì `QuoteEvaluation`: model này bị `nodes/` đọc gián
    # tiếp qua state, và một `QuoteEvaluation` hỏng không được làm chết lượt —
    # `QuoteEvaluation.from_raw` đã lo việc dựng lại an toàn ở đúng chỗ cần nó.
    last_quote_evaluation: dict[str, Any] | None = None
    last_quote_sent_at: datetime | None = None

    def with_quote(self, evaluation: Mapping[str, Any], sent_at: datetime) -> FormState:
        """Ghi nhớ đánh giá của báo giá vừa gửi."""

        return self.model_copy(
            update={
                "last_quote_evaluation": dict(evaluation),
                "last_quote_sent_at": sent_at,
            }
        )

    @property
    def has_quote_memory(self) -> bool:
        """Phiên này đã từng gửi đi một báo giá được đánh giá hay chưa."""

        return self.last_quote_evaluation is not None


def _coerce_vehicle_type(value: SlotValue) -> VehicleType | None:
    if isinstance(value, VehicleType):
        return value
    try:
        return VehicleType(str(value))
    except ValueError:
        return None


def get_next_missing_field(form: VehicleInquiryForm) -> str | None:
    """Field kế tiếp cần hỏi, hoặc `None` khi form đã đủ — thuần, KHÔNG gọi LLM.

    Uỷ quyền cho `slot_policy.next_slot` thay vì chép lại thứ tự ưu tiên: hai bản
    sao của cùng một cây slot sẽ lệch nhau ngay lần đầu ai đó sửa một bên.
    """

    slots = {SlotName(name): value for name, value in form.to_slots().items()}
    slot = next_slot(form.vehicle_type, slots)
    return slot.value if slot is not None else None
