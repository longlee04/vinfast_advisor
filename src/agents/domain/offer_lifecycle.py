"""Vòng đời ưu đãi gắn cơ hội + hàng rào an toàn (plan Customer 360 §2.4, Phase 5B).

SUGGESTED → APPROVED → SENT → ENGAGED → CONVERTED | EXPIRED (và DISMISSED khi TVV/quản lý bỏ).
Hàng rào — kiểm ở đây, bằng code, trước MỌI lần gửi:
- chỉ ưu đãi ACTIVE và còn hạn NGAY LÚC gửi; `UNVERIFIED` tuyệt đối không tới khách;
- còn suất (`used_count < max_uses`);
- vượt `advisor_max_discount_vnd` (hoặc ngưỡng chưa cấu hình mà có tiền — Q5) → quản lý duyệt.

THUẦN Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final


class OfferStatus(StrEnum):
    SUGGESTED = "SUGGESTED"
    APPROVED = "APPROVED"
    SENT = "SENT"
    ENGAGED = "ENGAGED"
    CONVERTED = "CONVERTED"
    EXPIRED = "EXPIRED"
    DISMISSED = "DISMISSED"


TRANSITIONS: Final[dict[OfferStatus, frozenset[OfferStatus]]] = {
    OfferStatus.SUGGESTED: frozenset({OfferStatus.APPROVED, OfferStatus.DISMISSED, OfferStatus.EXPIRED}),
    OfferStatus.APPROVED: frozenset({OfferStatus.SENT, OfferStatus.DISMISSED, OfferStatus.EXPIRED}),
    OfferStatus.SENT: frozenset({OfferStatus.ENGAGED, OfferStatus.CONVERTED, OfferStatus.EXPIRED}),
    OfferStatus.ENGAGED: frozenset({OfferStatus.CONVERTED, OfferStatus.EXPIRED}),
    OfferStatus.CONVERTED: frozenset(),
    OfferStatus.EXPIRED: frozenset(),
    OfferStatus.DISMISSED: frozenset(),
}
#: Còn sống — một cơ hội chỉ có một ưu đãi sống cho mỗi mã (unique partial index).
LIVE_STATUSES: Final[frozenset[OfferStatus]] = frozenset(
    {OfferStatus.SUGGESTED, OfferStatus.APPROVED, OfferStatus.SENT, OfferStatus.ENGAGED}
)


class OfferTransitionError(ValueError):
    def __init__(self, current: OfferStatus, target: OfferStatus) -> None:
        super().__init__(f"{current.value} → {target.value} không hợp lệ")
        self.current = current
        self.target = target


class SendBlocked(StrEnum):
    """Lý do KHÔNG được gửi — trả nguyên cho TVV, không đoán."""

    NOT_APPROVED = "NOT_APPROVED"
    NEEDS_MANAGER = "NEEDS_MANAGER"
    PROMOTION_NOT_ACTIVE = "PROMOTION_NOT_ACTIVE"
    PROMOTION_EXPIRED = "PROMOTION_EXPIRED"
    NO_USES_LEFT = "NO_USES_LEFT"
    NO_OPEN_SESSION = "NO_OPEN_SESSION"


@dataclass(frozen=True, slots=True)
class PromotionGate:
    """Ảnh chụp ưu đãi tại thời điểm kiểm — đọc từ `promotions` ngay trước khi gửi."""

    status: str
    valid_from: datetime
    valid_to: datetime | None
    max_uses: int | None
    used_count: int
    advisor_max_discount_vnd: int | None


def check_transition(current: OfferStatus, target: OfferStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise OfferTransitionError(current, target)


def needs_manager_approval(discount_vnd: int | None, advisor_max_discount_vnd: int | None) -> bool:
    """Có tiền mà vượt ngưỡng TVV — hoặc ngưỡng chưa cấu hình (Q5: mặc định chặt)."""

    if not discount_vnd:
        return False
    return advisor_max_discount_vnd is None or discount_vnd > advisor_max_discount_vnd


def initial_status(needs_manager: bool) -> OfferStatus:
    """TVV tạo đề xuất = TVV đã duyệt phần mình; vượt ngưỡng thì chờ quản lý."""

    return OfferStatus.SUGGESTED if needs_manager else OfferStatus.APPROVED


def promotion_blocker(gate: PromotionGate | None, at: datetime) -> SendBlocked | None:
    if gate is None or gate.status != "ACTIVE":
        return SendBlocked.PROMOTION_NOT_ACTIVE
    if gate.valid_from > at or (gate.valid_to is not None and gate.valid_to < at):
        return SendBlocked.PROMOTION_EXPIRED
    if gate.max_uses is not None and gate.used_count >= gate.max_uses:
        return SendBlocked.NO_USES_LEFT
    return None


def send_blocker(status: OfferStatus, gate: PromotionGate | None, at: datetime) -> SendBlocked | None:
    """Hàng rào ngay lúc gửi. `None` = được gửi."""

    if status is OfferStatus.SUGGESTED:
        return SendBlocked.NEEDS_MANAGER
    if status is not OfferStatus.APPROVED:
        return SendBlocked.NOT_APPROVED
    return promotion_blocker(gate, at)


__all__ = [
    "LIVE_STATUSES",
    "TRANSITIONS",
    "OfferStatus",
    "OfferTransitionError",
    "PromotionGate",
    "SendBlocked",
    "check_transition",
    "initial_status",
    "needs_manager_approval",
    "promotion_blocker",
    "send_blocker",
]
