"""Liên hệ tính năng THẬT của xe với nhu cầu khách vừa nói — bằng dữ liệu, không bằng LLM.

Sếp 2026-08-29: "khi có nhu cầu, thói quen sử dụng thì phải lấy được tính năng
của xe phù hợp với nhu cầu đó, cố liên hệ tính năng trên xe với nhu cầu". Và lo
LLM bịa: bịa *sự thật* (xe có tính năng nó không có) đã có guardrail; bịa *lợi
ích* ("điều hoà 2 chiều giúp đi phố dễ chịu") là do KHÔNG CÓ dữ liệu — bảng
định nghĩa tính năng chỉ có mã + tên.

Dữ liệu lợi ích nằm ở bảng `feature_need_tags` (cột `note`): mỗi cặp (tính
năng, nhu cầu) một câu lợi ích đã duyệt, đội sửa được mà không đụng code. Module
này chỉ làm ba việc thuần:

1. Suy nhãn nhu cầu (tập ĐÓNG, đúng 8 nhãn đang có trong DB) từ slot đã lưu:
   mục đích, quãng đường, số người, sạc tại nhà, thói quen khách kể.
2. Chọn cặp (tính năng xe CÓ THẬT ∩ nhu cầu) theo độ liên quan.
3. Dựng câu "Hợp với nhu cầu … của anh/chị: <tính năng> — <lợi ích>".

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from src.agents.domain.need_tags import canonical_need_tag
from src.agents.domain.slot_mapping import purpose_bucket_for
from src.agents.domain.values import PurposeBucket, SlotName
from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS

#: Tám nhãn nhu cầu ĐANG CÓ trong `feature_need_tags` — nguồn sự thật là DB, không
#: phải enum nào trong code. Thứ tự = thứ tự ưu tiên khi khách có nhiều nhu cầu.
NEED_TAG_LABELS: Final[dict[str, str]] = {
    "URBAN_TRAFFIC": "đi lại trong phố",
    "FAMILY_TRIP": "chở gia đình",
    "LONG_RANGE": "đi xa, đi tỉnh",
    "DELIVERY_LOAD": "chở hàng nặng",
    "DELIVERY_USE": "chạy giao hàng, dịch vụ",
    "NO_HOME_CHARGING": "không sạc được ở nhà",
    "ECO_SAVING": "tiết kiệm chi phí",
    "PREMIUM_COMFORT": "tiện nghi cao cấp",
}

_BUCKET_TAGS: Final[dict[PurposeBucket, tuple[str, ...]]] = {
    PurposeBucket.WORK: ("URBAN_TRAFFIC",),
    # "cá nhân" quá mơ hồ để gán nhu cầu — không đoán.
    PurposeBucket.PERSONAL: (),
    PurposeBucket.FAMILY: ("FAMILY_TRIP",),
    PurposeBucket.LONG_TRIP: ("LONG_RANGE",),
    PurposeBucket.DELIVERY: ("DELIVERY_USE", "DELIVERY_LOAD"),
    PurposeBucket.SERVICE: ("DELIVERY_USE", "ECO_SAVING"),
}

#: Nhãn thói quen LLM/khách kể có thể mang tên cũ; quy về nhãn DB.
_LEGACY_TAGS: Final[dict[str, str]] = {
    "LONG_DISTANCE": "LONG_RANGE",
    "HIGHWAY_SAFETY": "LONG_RANGE",
    "FAMILY_LARGE": "FAMILY_TRIP",
    "LOW_OPERATING_COST": "ECO_SAVING",
    "TIGHT_BUDGET": "ECO_SAVING",
}

MAX_FITS_PER_VEHICLE: Final[int] = 3


@dataclass(frozen=True, slots=True)
class FeatureFit:
    """Một cặp (tính năng xe có thật, nhu cầu) kèm câu lợi ích đã duyệt."""

    feature_code: str
    feature_name: str
    need_tag: str
    relevance: Decimal
    note: str

    @property
    def label(self) -> str:
        return FEATURE_DISPLAY_LABELS.get(self.feature_code) or self.feature_name


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def need_tags_from_slots(slots: Mapping[str, Any]) -> tuple[str, ...]:
    """Nhãn nhu cầu suy từ slot đã lưu, chỉ trả nhãn có trong `NEED_TAG_LABELS`.

    Tất định, không đọc chữ tự do ngoài `purpose_bucket_for` (đã có keyword map).
    """

    tags: set[str] = set()
    raw_habits = slots.get(SlotName.HABIT_NEED_TAGS.value)
    if isinstance(raw_habits, str):
        raw_habits = [raw_habits]
    if isinstance(raw_habits, list | tuple):
        for item in raw_habits:
            if not isinstance(item, str) or not item.strip() or item.startswith("__"):
                continue
            key = canonical_need_tag(item)
            key = _LEGACY_TAGS.get(key, key)
            if key in NEED_TAG_LABELS:
                tags.add(key)
    purpose = slots.get(SlotName.PURPOSE.value)
    has_purpose = isinstance(purpose, str) and purpose.strip() and not purpose.startswith("__")
    if has_purpose or isinstance(slots.get(SlotName.PURPOSE_BUCKET.value), str):
        typed: dict[SlotName, Any] = {}
        for name in (SlotName.PURPOSE, SlotName.PURPOSE_BUCKET):
            if slots.get(name.value) is not None:
                typed[name] = slots[name.value]
        bucket = purpose_bucket_for(typed)
        tags.update(_BUCKET_TAGS.get(bucket, ()))
    distance = _decimal(slots.get(SlotName.REQUIRED_RANGE_KM.value))
    if distance is not None and distance >= Decimal("150"):
        tags.add("LONG_RANGE")
    elif distance is not None and Decimal("0") < distance < Decimal("50"):
        tags.add("URBAN_TRAFFIC")
    passengers = _decimal(slots.get(SlotName.PASSENGER_COUNT.value))
    if passengers is not None and passengers >= Decimal("5"):
        tags.add("FAMILY_TRIP")
    if slots.get(SlotName.HOME_CHARGING.value) is False:
        tags.add("NO_HOME_CHARGING")
    return tuple(tag for tag in NEED_TAG_LABELS if tag in tags)


def select_fits(
    fits: Iterable[FeatureFit],
    need_tags: Sequence[str],
    *,
    limit: int = MAX_FITS_PER_VEHICLE,
) -> list[FeatureFit]:
    """Mỗi tính năng một lần, XOAY VÒNG qua các nhu cầu để nhu cầu nào cũng có mặt.

    Đo local 2026-08-29: khách kể "gia đình 5 người, hay đi chơi xa" mà cả ba tính
    năng chọn ra đều thuộc nhu cầu đứng đầu — nhu cầu gia đình bị lấn hết. Xoay
    vòng: mỗi nhu cầu lấy cặp liên quan nhất, rồi mới lấy tiếp vòng hai.
    """

    order = {tag: index for index, tag in enumerate(need_tags)}
    queues: dict[str, list[FeatureFit]] = {tag: [] for tag in need_tags}
    for fit in sorted(
        (f for f in fits if f.need_tag in order and f.note.strip()),
        key=lambda f: (-f.relevance, f.feature_code),
    ):
        queues[fit.need_tag].append(fit)
    chosen: dict[str, FeatureFit] = {}
    while len(chosen) < limit and any(queues.values()):
        for tag in need_tags:
            while queues[tag]:
                fit = queues[tag].pop(0)
                if fit.feature_code not in chosen:
                    chosen[fit.feature_code] = fit
                    break
            if len(chosen) >= limit:
                break
    return list(chosen.values())


def fit_line(fits: Sequence[FeatureFit], need_tags: Sequence[str]) -> str:
    """ "Hợp với nhu cầu đi lại trong phố của anh/chị: Kích thước nhỏ gọn — …; …"

    Rỗng khi không có cặp nào: không có câu đã duyệt thì không bình luận.
    """

    chosen = select_fits(fits, need_tags)
    if not chosen:
        return ""
    used_tags = [tag for tag in need_tags if any(f.need_tag == tag for f in chosen)]
    needs = " và ".join(NEED_TAG_LABELS[tag] for tag in used_tags[:2])
    parts = [f"{fit.label} — {fit.note.strip().rstrip('.')}" for fit in chosen]
    return f"Hợp với nhu cầu {needs} của anh/chị: " + "; ".join(parts) + "."


__all__ = [
    "MAX_FITS_PER_VEHICLE",
    "NEED_TAG_LABELS",
    "FeatureFit",
    "fit_line",
    "need_tags_from_slots",
    "select_fits",
]
