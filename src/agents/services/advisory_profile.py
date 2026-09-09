"""Hồ sơ khách đã đủ để chấm điểm chưa — dùng chung cho các node.

Đặt ở `services/` chứ không `domain/`: `nodes/` được phép phụ thuộc `services/`
nhưng KHÔNG được phụ thuộc `domain/` (luật 6.5b, có test canh ở
`tests/agents/integration/test_graph_boundary.py`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

#: Tiêu chí đủ để CHẤM ĐIỂM. Có bất kỳ cái nào là khách đã nói nhu cầu thật.
#:
#: `vehicle_type` KHÔNG nằm đây: nó chọn nhánh, không phải một nhu cầu.
ADVISORY_CRITERION_SLOTS: Final[tuple[str, ...]] = (
    "budget_max_vnd",
    "budget_min_vnd",
    "budget_stated_vnd",
    "passenger_count",
    "purpose",
    "purpose_bucket",
    "habit_need_tags",
    "required_range_km",
    "max_load_kg",
)


def has_advisory_criteria(slots: object) -> bool:
    """Khách đã nói đủ để đề xuất chưa."""

    if not isinstance(slots, Mapping):
        return False
    return any(slots.get(name) is not None for name in ADVISORY_CRITERION_SLOTS)


__all__ = ["ADVISORY_CRITERION_SLOTS", "has_advisory_criteria"]
