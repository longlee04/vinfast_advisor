"""Độ nóng của một cơ hội (plan Customer 360 §5.2, `[GIẢ ĐỊNH G7]`).

Công thức cộng điểm có trọng số, tính ở BACKEND; frontend chỉ đọc `heat_score`,
`heat_band` và `heat_breakdown` để giải thích "vì sao nóng". Đổi trọng số thì tăng
`HEAT_VERSION` để phân biệt điểm cũ/mới khi so sánh.

THUẦN Python: không SQLAlchemy/FastAPI/LLM SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.sales_stage import SalesStage

HEAT_VERSION: Final[str] = "h1"
HOT_THRESHOLD: Final[int] = 60
WARM_THRESHOLD: Final[int] = 30
#: Cơ hội không được nhắc lại quá số ngày này thì chuyển DORMANT (G15).
DORMANT_AFTER_DAYS: Final[int] = 30
DORMANT_HEAT_CAP: Final[int] = 15

STAGE_POINTS: Final[dict[SalesStage, int]] = {
    SalesStage.DISCOVER: 0,
    SalesStage.COMPARE: 10,
    SalesStage.QUOTE: 25,
    SalesStage.TEST_DRIVE: 35,
    SalesStage.CLOSE: 45,
}
TIMEFRAME_POINTS: Final[dict[str, int]] = {"WITHIN_1_MONTH": 20, "1_3_MONTHS": 10}
PHONE_POINTS: Final[int] = 10
HUMAN_REQUESTED_POINTS: Final[int] = 10
BUDGET_POINTS: Final[int] = 5
PAYMENT_POINTS: Final[int] = 5
EVADED_POINTS_PER_SLOT: Final[int] = -5
EVADED_POINTS_FLOOR: Final[int] = -10


class HeatBand(StrEnum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


@dataclass(frozen=True, slots=True)
class HeatSignals:
    stage: SalesStage
    purchase_timeframe: str | None = None
    has_phone: bool = False
    human_requested: bool = False
    #: Số phiên tư vấn gắn cơ hội trong 14 ngày gần nhất.
    sessions_14d: int = 0
    budget_stated: bool = False
    payment_asked: bool = False
    #: Số slot bị hỏi ≥ 2 lần mà vẫn trống.
    evaded_slots: int = 0
    days_since_seen: float = 0.0


@dataclass(frozen=True, slots=True)
class HeatPart:
    code: str
    points: int
    detail: str


@dataclass(frozen=True, slots=True)
class HeatResult:
    score: int
    band: HeatBand
    breakdown: tuple[HeatPart, ...]
    dormant: bool


def band_for(score: int) -> HeatBand:
    if score >= HOT_THRESHOLD:
        return HeatBand.HOT
    if score >= WARM_THRESHOLD:
        return HeatBand.WARM
    return HeatBand.COLD


def _recency_points(days: float) -> int:
    if days <= 3:
        return 0
    if days <= 7:
        return -5
    if days <= 14:
        return -15
    return -25


def compute_heat(signals: HeatSignals) -> HeatResult:
    """Điểm 0..100 kèm từng phần cộng/trừ (bảng §5.2)."""

    parts = [HeatPart("H1", STAGE_POINTS[signals.stage], signals.stage.value)]
    timeframe = TIMEFRAME_POINTS.get(signals.purchase_timeframe or "", 0)
    if timeframe:
        parts.append(HeatPart("H2", timeframe, signals.purchase_timeframe or ""))
    if signals.has_phone:
        parts.append(HeatPart("H3", PHONE_POINTS, "Có SĐT"))
    if signals.human_requested:
        parts.append(HeatPart("H4", HUMAN_REQUESTED_POINTS, "Đòi gặp tư vấn viên"))
    if signals.sessions_14d >= 3:
        parts.append(HeatPart("H5", 10, f"{signals.sessions_14d} phiên/14 ngày"))
    elif signals.sessions_14d == 2:
        parts.append(HeatPart("H5", 5, "2 phiên/14 ngày"))
    if signals.budget_stated:
        parts.append(HeatPart("H6", BUDGET_POINTS, "Nêu ngân sách"))
    if signals.payment_asked:
        parts.append(HeatPart("H7", PAYMENT_POINTS, "Hỏi thanh toán"))
    if signals.evaded_slots > 0:
        parts.append(
            HeatPart(
                "H8",
                max(EVADED_POINTS_FLOOR, EVADED_POINTS_PER_SLOT * signals.evaded_slots),
                f"Né {signals.evaded_slots} câu hỏi",
            )
        )
    dormant = signals.days_since_seen > DORMANT_AFTER_DAYS
    recency = _recency_points(signals.days_since_seen)
    if recency:
        parts.append(HeatPart("H9", recency, f"{int(signals.days_since_seen)} ngày chưa quay lại"))
    score = max(0, min(100, sum(part.points for part in parts)))
    if dormant:
        score = min(score, DORMANT_HEAT_CAP)
    return HeatResult(score=score, band=band_for(score), breakdown=tuple(parts), dormant=dormant)


__all__ = [
    "DORMANT_AFTER_DAYS",
    "HEAT_VERSION",
    "HOT_THRESHOLD",
    "WARM_THRESHOLD",
    "HeatBand",
    "HeatPart",
    "HeatResult",
    "HeatSignals",
    "band_for",
    "compute_heat",
]
