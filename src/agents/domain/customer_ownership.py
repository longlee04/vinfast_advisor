"""Ai phụ trách khách — tư vấn viên TỰ NHẬN, không còn Admin gán tay.

Ba cách một khách đổi người phụ trách:

- **Tiếp quản** hội thoại (`POST /advisor/conversations/{id}/join`): khách chưa có ai phụ
  trách thì thuộc về người vừa tiếp quản. Khách đã có người khác phụ trách thì giữ nguyên.
- **Nhận khách** từ hàng chờ "khách chưa ai phụ trách".
- **Nhả**: tư vấn viên tự trả khách về hàng chờ, hoặc hệ thống tự nhả khi không có hoạt
  động tư vấn viên nào với khách trong `RELEASE_AFTER_DAYS` ngày.

Ràng buộc "mỗi khách một người" nằm ở database (unique index một phần, agent_0040), nên
hai người bấm cùng lúc thì đúng một người thắng. THUẦN Python.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

#: Không có hoạt động tư vấn viên với khách trong chừng này ngày → khách về lại hàng chờ.
RELEASE_AFTER_DAYS: Final[int] = 7

#: `customer_advisor_assignments.assigned_by` cho hai đường tự nhận.
VIA_TAKEOVER: Final = "TAKEOVER"
VIA_CLAIM: Final = "SELF_CLAIM"

#: `status` khi khách rời người phụ trách (khác `TRANSFERRED`/`UNASSIGNED` của luồng Admin cũ).
STATUS_RELEASED: Final = "RELEASED"
REASON_SELF_RELEASE: Final = "Tư vấn viên trả khách về hàng chờ"
REASON_STALE: Final = f"Không có hoạt động tư vấn viên trong {RELEASE_AFTER_DAYS} ngày"


class ClaimOutcome(StrEnum):
    CLAIMED = "CLAIMED"
    ALREADY_MINE = "ALREADY_MINE"
    TAKEN = "TAKEN"


def claim_outcome(inserted: bool, owner: str | None, requester_ids: tuple[str, ...]) -> ClaimOutcome:
    """Kết quả một lần nhận: ghi được dòng mới → CLAIMED; không ghi được thì xem ai đang giữ."""

    if inserted:
        return ClaimOutcome.CLAIMED
    if owner is not None and owner in requester_ids:
        return ClaimOutcome.ALREADY_MINE
    return ClaimOutcome.TAKEN


def stale_before(now: datetime) -> datetime:
    """Mốc: hoạt động tư vấn viên cuối cùng cũ hơn mốc này thì khách bị tự nhả."""

    return now - timedelta(days=RELEASE_AFTER_DAYS)


__all__ = [
    "REASON_SELF_RELEASE",
    "REASON_STALE",
    "RELEASE_AFTER_DAYS",
    "STATUS_RELEASED",
    "VIA_CLAIM",
    "VIA_TAKEOVER",
    "ClaimOutcome",
    "claim_outcome",
    "stale_before",
]
