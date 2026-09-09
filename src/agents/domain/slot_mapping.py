"""[A3-3] Anh xa slot da xac nhan sang tham so Lop 1 va trong so xep hang.

Muc dich su dung la preference, khong phai hard filter, tru nhanh giao hang
cua xe may dien, noi `max_load_kg` la dieu kien cung — `_is_delivery` la noi
DUY NHAT phan loai nhom muc dich la hard filter (khong chi ranking), nen phai
uu tien slot LLM da dong goi qua `purpose_bucket_for`, khong duoc chi keyword-
match tren `PURPOSE` nhu cac tieu chi ranking khac.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from src.agents.contracts import FilterCriteria
from src.agents.domain.slot_tree import is_applicable
from src.agents.domain.values import PurposeBucket, SlotName, SlotValue, VehicleType, is_declined

DELIVERY_PURPOSE_KEYWORDS: frozenset[str] = frozenset(
    {"giao hàng", "giao hang", "ship", "shipper", "chở hàng", "cho hang"}
)

# T7 (7A): nhóm mục đích cho allowlist feature — gộp vào slot_mapping, không tạo
# bảng thứ hai.
FAMILY_PURPOSE_KEYWORDS: frozenset[str] = frozenset({"gia đình", "gia dinh", "chở gia đình", "cho gia dinh"})
WORK_PURPOSE_KEYWORDS: frozenset[str] = frozenset({"đi làm", "di lam", "đi làm", "công sở", "cong so", "đưa đón"})
SERVICE_PURPOSE_KEYWORDS: frozenset[str] = frozenset({"dịch vụ", "dich vu", "kinh doanh", "chạy xe"})
#: Đi tỉnh / về quê / đường dài. Kiểm SAU `FAMILY`: "chở gia đình về quê" là một
#: chuyến gia đình, và khoang hành lý mới là thứ quyết định ở đó.
LONG_TRIP_PURPOSE_KEYWORDS: frozenset[str] = frozenset(
    {
        "về quê",
        "ve que",
        "đi xa",
        "di xa",
        "đi tỉnh",
        "di tinh",
        "đường dài",
        "duong dai",
        "đường trường",
        "duong truong",
        "du lịch",
        "du lich",
    }
)
DELIVERY_BUCKET_KEYWORDS = DELIVERY_PURPOSE_KEYWORDS

# Nhãn tiếng Việt cho câu hỏi lượt 2 ("Với nhu cầu {nhãn}, ...", design doc mục
# "Lượt 2"). UNKNOWN không có nhãn — câu hỏi bỏ hẳn phần mở đầu khi chưa suy được
# mục đích, tránh nói "với nhu cầu unknown".
PURPOSE_BUCKET_LABEL: Mapping[PurposeBucket, str] = {
    PurposeBucket.FAMILY: "gia đình",
    PurposeBucket.WORK: "đi làm",
    PurposeBucket.SERVICE: "dịch vụ",
    PurposeBucket.DELIVERY: "giao hàng",
    PurposeBucket.LONG_TRIP: "đi xa",
    PurposeBucket.PERSONAL: "cá nhân",
}


_PURPOSE_WEIGHT = 1.0
_HABIT_TAG_WEIGHT = 0.8


def _int_or_none(value: SlotValue) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def purpose_bucket(purpose: SlotValue) -> PurposeBucket:
    """Suy nhóm mục đích từ chuỗi `purpose` bằng keyword; mặc định UNKNOWN."""
    if not isinstance(purpose, str):
        return PurposeBucket.UNKNOWN
    # Gạch dưới → khoảng trắng: slot `purpose` có HAI nguồn viết khác nhau —
    # LLM trích ra chữ tự do ("chở gia đình đi xa") còn dữ liệu cũ và test dùng
    # token gạch dưới ("gia_dinh", "di_lam"). Không nắn thì mọi token gạch dưới
    # rơi hết về `PERSONAL`, tức mất sạch nhóm mục đích của những phiên cũ.
    lowered = purpose.casefold().replace("_", " ")
    if any(keyword in lowered for keyword in FAMILY_PURPOSE_KEYWORDS):
        return PurposeBucket.FAMILY
    if any(keyword in lowered for keyword in WORK_PURPOSE_KEYWORDS):
        return PurposeBucket.WORK
    if any(keyword in lowered for keyword in SERVICE_PURPOSE_KEYWORDS):
        return PurposeBucket.SERVICE
    if any(keyword in lowered for keyword in DELIVERY_BUCKET_KEYWORDS):
        return PurposeBucket.DELIVERY
    if any(keyword in lowered for keyword in LONG_TRIP_PURPOSE_KEYWORDS):
        return PurposeBucket.LONG_TRIP
    return PurposeBucket.PERSONAL


def purpose_bucket_for(known_slots: Mapping[SlotName, SlotValue]) -> PurposeBucket:
    """Nhóm mục đích: ưu tiên slot LLM đã đóng gói (`PURPOSE_BUCKET`), rơi về
    keyword-match trên `PURPOSE` khi lượt đó LLM chưa điền (T7 mở rộng)."""
    persisted = known_slots.get(SlotName.PURPOSE_BUCKET)
    if isinstance(persisted, str):
        try:
            return PurposeBucket(persisted)
        except ValueError:
            pass
    return purpose_bucket(known_slots.get(SlotName.PURPOSE))


def _is_delivery(known_slots: Mapping[SlotName, SlotValue]) -> bool:
    return purpose_bucket_for(known_slots) is PurposeBucket.DELIVERY


def to_filter_criteria(vehicle_type: VehicleType, known_slots: Mapping[SlotName, SlotValue]) -> FilterCriteria:
    """Chi slot dinh luong phu hop moi thanh dieu kien SQL."""
    budget = known_slots.get(SlotName.BUDGET_MAX_VND)
    budget_max_vnd = Decimal(str(budget)) if isinstance(budget, (int, float)) and not isinstance(budget, bool) else None
    passenger_count = (
        _int_or_none(known_slots.get(SlotName.PASSENGER_COUNT))
        if is_applicable(vehicle_type, SlotName.PASSENGER_COUNT)
        else None
    )
    required_load_kg = (
        _int_or_none(known_slots.get(SlotName.MAX_LOAD_KG))
        if is_applicable(vehicle_type, SlotName.MAX_LOAD_KG) and _is_delivery(known_slots)
        else None
    )
    return FilterCriteria(
        vehicle_type=vehicle_type,
        budget_max_vnd=budget_max_vnd,
        passenger_count=passenger_count,
        required_range_km=_int_or_none(known_slots.get(SlotName.REQUIRED_RANGE_KM)),
        required_load_kg=required_load_kg,
    )


def preference_weights(known_slots: Mapping[SlotName, SlotValue]) -> dict[str, float]:
    """Tao trong so xep hang, khong loai xe khoi tap ung vien."""
    weights: dict[str, float] = {}
    purpose = known_slots.get(SlotName.PURPOSE)
    if isinstance(purpose, str) and purpose.strip() and not is_declined(purpose):
        weights[f"PURPOSE::{purpose.strip().casefold()}"] = _PURPOSE_WEIGHT
    tags = known_slots.get(SlotName.HABIT_NEED_TAGS)
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag.strip() and not is_declined(tag):
                weights[tag.strip()] = _HABIT_TAG_WEIGHT
    return weights
