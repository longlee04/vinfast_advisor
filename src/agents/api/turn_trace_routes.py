"""HTTP cho màn admin "vì sao agent đáp như vậy" (Sếp 2026-08-26).

Chỉ ADMIN. Vệt quyết định chứa nguyên văn câu khách nói, nên nó là dữ liệu hội
thoại — cùng mức bảo vệ với `analytics_routes`, không nới ra cho tư vấn viên.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from src.agents.api.security import StaffIdentity, require_admin
from src.agents.services.operations.turn_trace import TurnTraceOperations

router = APIRouter(prefix="/agent/turn-traces", tags=["agent-turn-traces"])


def turn_trace_operations() -> TurnTraceOperations:
    """Điểm nối use case — composition của app thật ghi đè bằng bản có DB."""

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Chưa nối use case vệt quyết định",
    )


class TraceSummaryResponse(BaseModel):
    """Số liệu tổng hợp một khung thời gian."""

    model_config = ConfigDict(frozen=True)

    total: int
    with_intent: int
    coverage_pct: float
    tier_counts: dict[str, int]
    histogram: dict[str, int]


@router.get("/stats", response_model=TraceSummaryResponse)
async def read_stats(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    _identity: StaffIdentity = Depends(require_admin),
    operations: TurnTraceOperations = Depends(turn_trace_operations),
) -> TraceSummaryResponse:
    """Độ phủ ý định, phân bố mức, biểu đồ confidence."""

    summary = await operations.stats(hours=hours)
    return TraceSummaryResponse(
        total=summary.total,
        with_intent=summary.with_intent,
        coverage_pct=summary.coverage_pct,
        tier_counts=summary.tier_counts,
        histogram=summary.histogram,
    )


@router.get("")
async def read_recent(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    limit: int = Query(default=50, ge=1, le=200),
    tier: str | None = Query(default=None),
    _identity: StaffIdentity = Depends(require_admin),
    operations: TurnTraceOperations = Depends(turn_trace_operations),
) -> dict:
    """Các lượt gần nhất kèm TRỌN vệt giải thích.

    `payload` trả nguyên vẹn: nó chính là phần "vì sao" — bảng điểm ý định,
    entity đã khớp, nhãn LLM, và cờ của các cửa tất định.
    """

    return {"items": await operations.recent(hours=hours, limit=limit, tier=tier)}
