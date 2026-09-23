"""[A3-1] Cây slot phân nhánh theo loại phương tiện (mục 7.0 vehicle-catalog-schema).

Bảng tra cứu tường minh, KHÔNG để LLM quyết định hỏi gì tiếp (mục 6.8). Lượt 1 chỉ
CHỦ ĐỘNG hỏi ngân sách, nhu cầu (mục đích) và số người dùng — `REQUIRED_RANGE_KM`
và `HOME_CHARGING` không nằm trong nhóm hỏi lượt 1 nữa (feedback thật 2026-08-21:
khách đã trả lời "khoảng tầm 30km" vẫn bị hỏi lại, và hai slot này không cần hỏi
ngay — "khai thác các thông tin khác vào nhu cầu" ở lượt 2 thay vì hỏi thẳng).
Khách tự nguyện nhắc tới quãng đường/sạc tại nhà thì vẫn được trích xuất và ghi
nhận bình thường (`_TYPE_AGNOSTIC_OPENING`, `is_applicable`), chỉ là agent không
chủ động hỏi. `PASSENGER_COUNT` chỉ áp nhánh ô tô nên vẫn chờ biết loại xe mới
hỏi. Nếu khách chủ động nói ngân sách trước, slot đó được giữ lại khi biết loại xe.

`PASSENGER_COUNT`, `PURPOSE`, `HABIT_NEED_TAGS` và các ràng buộc sử dụng vẫn nằm
trong cây để chuẩn hoá thông tin khách tự nguyện cung cấp. Policy price-first không
ép hỏi các slot này: chỉ loại xe và ngân sách là đủ để tra catalog; slot tự nguyện
được dùng để lọc/xếp hạng tốt hơn khi có.

`MAX_LOAD_KG` không nằm trong `SLOT_ORDER`: nó chỉ nổ ở nhánh giao hàng của xe
máy điện, suy ra từ `PURPOSE` chứ không hỏi tuần tự (A3-3).
"""

from __future__ import annotations

from src.agents.domain.values import SlotName, VehicleType

FIRST_SLOT: SlotName = SlotName.VEHICLE_TYPE

#: Nhóm slot hỏi GỘP trong lượt 1 (T5, thu hẹp 2026-08-21 rồi 2026-08-26).
#:
#: **PASSENGER_COUNT đã bỏ khỏi nhóm hỏi** (Sếp 2026-08-26): nó chỉ CỘNG ĐIỂM
#: xếp hạng (`domain/scoring` line ~382 — `if profile.passenger_count and …`),
#: không lọc bỏ ứng viên nào, nên thiếu nó thì đề xuất kém sắc chứ không sai.
#: Đổi lại, câu hỏi mục đích ở `prompts/combined_intake` giờ là câu MỞ kèm ví dụ
#: "chở gia đình 5 người" — khách nói số người trong đó thì vẫn nhặt được y hệt,
#: mà không tốn một mục đánh số riêng.
#:
#: Cả hai nhánh giờ dùng CHUNG một nhóm: ngân sách + mục đích.
#: KHÔNG hỏi REQUIRED_RANGE_KM/HOME_CHARGING ở lượt này.
OPENING_GROUP: tuple[SlotName, ...] = (
    SlotName.BUDGET_MAX_VND,
    SlotName.PURPOSE,
)

#: Giữ tên cũ làm bí danh: nhánh xe máy và đường lui "chưa biết loại xe" đều trỏ
#: về cùng một nhóm kể từ khi PASSENGER_COUNT rời nhóm hỏi.
_PURPOSE_OPENING_GROUP: tuple[SlotName, ...] = OPENING_GROUP


def opening_group_for(
    vehicle_type: VehicleType | None,
    *,
    vehicle_type_exhausted: bool = False,
) -> tuple[SlotName, ...]:
    """Nhóm slot lượt 1 theo nhánh — ô tô giữ dòng ghép chỗ ngồi + mục đích.

    CHƯA BIẾT loại xe thì KHÔNG có nhóm nào (Sếp 2026-08-25). Bản cũ trả về
    `_PURPOSE_OPENING_GROUP` cho cả trường hợp này, với ý đồ SUY loại xe từ mục
    đích thay vì hỏi thẳng. Hậu quả khách nhìn thấy: gõ "tôi muốn tư vấn" và bị
    hỏi ngay ngân sách + mục đích, không được chọn ô tô hay xe máy — mà hai
    nhánh đó có dải giá và bộ tiêu chí khác hẳn nhau, đoán sai là sai từ câu hỏi
    đầu tiên.

    Trả rỗng thì `_decide_ask_or_retrieve` rơi xuống `next_field`, và
    `SLOT_ORDER` của cả hai nhánh đều mở đầu bằng `VEHICLE_TYPE` — câu hỏi loại
    xe đứng riêng, kèm nút chọn (`nodes/ask_or_retrieve.VEHICLE_TYPE_CHOICES`).

    Đường SUY loại xe KHÔNG mất: `_decide_ask_or_retrieve` chạy
    `inferred_vehicle_type` TRƯỚC chỗ này, nên khách mở lời đã kèm thông tin
    ("tôi cần xe giao hàng") vẫn được điền loại xe rồi đi thẳng vào nhóm.
    """

    if vehicle_type is VehicleType.CAR:
        return OPENING_GROUP
    if vehicle_type is None:
        # ĐƯỜNG LUI: hỏi loại xe đã cạn quota mà khách vẫn không nói rõ. Giữ
        # rỗng ở đây thì lượt kế tiếp không còn câu hỏi nào để đặt — hội thoại
        # đứng hình. Rơi về nhóm cũ để MỤC ĐÍCH làm tín hiệu suy loại xe, đúng
        # cơ chế đã có từ trước.
        return _PURPOSE_OPENING_GROUP if vehicle_type_exhausted else ()
    return _PURPOSE_OPENING_GROUP


SLOT_ORDER: dict[VehicleType, tuple[SlotName, ...]] = {
    VehicleType.CAR: (
        SlotName.VEHICLE_TYPE,
        SlotName.PASSENGER_COUNT,
        SlotName.REQUIRED_RANGE_KM,
        SlotName.HOME_CHARGING,
        SlotName.BUDGET_MAX_VND,
        SlotName.PURPOSE,
        SlotName.HABIT_NEED_TAGS,
    ),
    VehicleType.ELECTRIC_MOTORBIKE: (
        SlotName.VEHICLE_TYPE,
        SlotName.PURPOSE,
        SlotName.REQUIRED_RANGE_KM,
        SlotName.HOME_CHARGING,
        SlotName.BUDGET_MAX_VND,
        SlotName.HABIT_NEED_TAGS,
    ),
}

_DELIVERY_ONLY: frozenset[SlotName] = frozenset({SlotName.MAX_LOAD_KG})

#: Slot hợp lệ ở MỌI nhánh nhưng không bao giờ được hỏi thành một lượt riêng.
#: `BUDGET_MIN_VND` được trích cùng lúc với trần từ chính một câu của khách
#: ("từ 300 đến 700 triệu"), nên đưa nó vào `SLOT_ORDER` sẽ sinh ra một câu hỏi
#: "sàn ngân sách của anh/chị là bao nhiêu" mà không ai muốn nghe. Nhưng nó PHẢI
#: `is_applicable`, nếu không `slot_extraction._drop_unsupported_slots` lặng lẽ
#: xoá nó ngay sau khi trích được.
#: `BUDGET_STATED_VND` cùng nhóm và cùng lý do — thiếu nó ở đây thì slot được
#: trích đúng, được ghi vào dict, rồi bị `_drop_unsupported_slots` xoá TRONG IM
#: LẶNG trước khi kịp lưu. Đó đúng là chuyện đã xảy ra 2026-08-25: code hai đường
#: trích đều đúng, hàm parse trả đúng 500 triệu, mà bảng `conversation_slots`
#: không bao giờ có hàng nào.
_NEVER_ASKED: frozenset[SlotName] = frozenset({SlotName.BUDGET_MIN_VND, SlotName.BUDGET_STATED_VND})

#: Slot chấp nhận được khi CHƯA biết loại xe, hỏi được hoặc khách tự nhắc dù
#: chưa biết loại xe. REQUIRED_RANGE_KM/HOME_CHARGING không còn trong nhóm hỏi
#: chủ động (`OPENING_GROUP`) nhưng vẫn hợp lệ khi khách tự nguyện cung cấp.
#: PASSENGER_COUNT không nằm trong đây vì chỉ áp nhánh ô tô.
_TYPE_AGNOSTIC_OPENING: frozenset[SlotName] = frozenset(
    {SlotName.BUDGET_MAX_VND, SlotName.REQUIRED_RANGE_KM, SlotName.HOME_CHARGING}
)


def slot_sequence(vehicle_type: VehicleType | None) -> tuple[SlotName, ...]:
    """Thứ tự hỏi của nhánh; chưa biết loại xe thì chỉ có đúng một slot để hỏi."""

    if vehicle_type is None:
        return (FIRST_SLOT,)
    return SLOT_ORDER[vehicle_type]


def is_applicable(vehicle_type: VehicleType | None, slot: SlotName) -> bool:
    """Slot có thuộc nhánh này không — dùng để loại slot LLM trích nhầm nhánh."""

    # `_NEVER_ASKED` (sàn ngân sách), `PURPOSE_BUCKET` và `REGISTRATION_PROVINCE`
    # đều không nằm trong `SLOT_ORDER` nhưng phải sống sót qua `_applicable_slots`
    # ở mọi nhánh xe — nếu không sẽ bị strip ngay sau khi LLM trả về. Đó đúng là
    # chuyện đã xảy ra với `BUDGET_STATED_VND` hôm 2026-08-25: trích đúng, ghi vào
    # dict, rồi biến mất TRONG IM LẶNG trước khi kịp lưu.
    if slot in _NEVER_ASKED or slot in (SlotName.PURPOSE_BUCKET, SlotName.REGISTRATION_PROVINCE):
        return True
    if vehicle_type is None:
        return slot is FIRST_SLOT or slot in _TYPE_AGNOSTIC_OPENING
    if slot in _DELIVERY_ONLY:
        return vehicle_type is VehicleType.ELECTRIC_MOTORBIKE
    return slot in SLOT_ORDER[vehicle_type]
