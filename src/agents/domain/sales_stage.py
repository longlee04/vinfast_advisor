"""Giai đoạn BÁN HÀNG của một cơ hội (plan Customer 360 §5.1).

Khác `core.state.Stage`: đó là chặng HỘI THOẠI của một phiên (đang hỏi slot, đã đề
xuất…), còn đây là khách đã đi tới đâu trên hành trình mua — gom từ mọi phiên của
cùng một cơ hội. Enum này là nguồn định nghĩa DUY NHẤT; frontend chỉ phản chiếu
(`frontend/src/types/customer360.ts`).

THUẦN Python: không SQLAlchemy/FastAPI/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final


class SalesStage(StrEnum):
    DISCOVER = "DISCOVER"
    COMPARE = "COMPARE"
    QUOTE = "QUOTE"
    TEST_DRIVE = "TEST_DRIVE"
    CLOSE = "CLOSE"


STAGE_ORDER: Final[tuple[SalesStage, ...]] = tuple(SalesStage)

#: Chặng hội thoại lõi v2 → giai đoạn bán hàng tối thiểu. `HANDED_OFF` không có mặt:
#: chuyển người không nói gì về việc khách đã đi tới đâu. `SCHEDULING`/`OFFER_REVIEW`
#: chỉ tính QUOTE — lái thử phải có LỊCH THẬT mới tính (G6).
CORE_STAGE_TO_SALES: Final[dict[str, SalesStage]] = {
    "GREETING": SalesStage.DISCOVER,
    "COLLECTING": SalesStage.DISCOVER,
    "RECOMMENDED": SalesStage.COMPARE,
    "CHOSEN": SalesStage.COMPARE,
    "COSTING": SalesStage.QUOTE,
    "SCHEDULING": SalesStage.QUOTE,
    "OFFER_REVIEW": SalesStage.QUOTE,
}


def stage_rank(stage: SalesStage) -> int:
    return STAGE_ORDER.index(stage)


def max_stage(stages: Iterable[SalesStage]) -> SalesStage:
    return max(stages, key=stage_rank, default=SalesStage.DISCOVER)


@dataclass(frozen=True, slots=True)
class StageSignals:
    """Tín hiệu đã quan sát được của MỘT cơ hội, gom từ các phiên gắn vào nó."""

    core_stages: frozenset[str] = field(default_factory=frozenset)
    has_recommendations: bool = False
    quote_sent: bool = False
    has_test_drive: bool = False
    offer_engaged: bool = False
    won: bool = False


def derive_stage(signals: StageSignals, current: SalesStage | None = None) -> SalesStage:
    """Giai đoạn = bậc CAO NHẤT mà tín hiệu chứng minh được; không bao giờ lùi so với `current`."""

    reached = [SalesStage.DISCOVER]
    reached.extend(CORE_STAGE_TO_SALES[stage] for stage in signals.core_stages if stage in CORE_STAGE_TO_SALES)
    if signals.has_recommendations:
        reached.append(SalesStage.COMPARE)
    if signals.quote_sent:
        reached.append(SalesStage.QUOTE)
    if signals.has_test_drive:
        reached.append(SalesStage.TEST_DRIVE)
    if signals.offer_engaged or signals.won:
        reached.append(SalesStage.CLOSE)
    if current is not None:
        reached.append(current)
    return max_stage(reached)


__all__ = [
    "CORE_STAGE_TO_SALES",
    "STAGE_ORDER",
    "SalesStage",
    "StageSignals",
    "derive_stage",
    "max_stage",
    "stage_rank",
]
