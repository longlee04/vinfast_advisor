"""Gắn một phiên vào đúng một cơ hội mua (plan Customer 360 §5.3, luật R0–R7).

Luật TẤT ĐỊNH chạy trước; chỉ ca mơ hồ (R7) mới cần LLM phân loại, và LLM trả lời
thấp tin thì TVV quyết bằng nút Tách/Gộp. Module này không gọi LLM — nó chỉ nói
"ca này mơ hồ, đây là các ứng viên" và áp kết luận của LLM khi được đưa vào.

THUẦN Python: không SQLAlchemy/FastAPI/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final

from src.agents.domain.buyer_for import BuyerFor

#: Dưới ngưỡng này kết luận của LLM chỉ là "gắn tạm", TVV phải xác nhận (G9).
LLM_CONFIDENCE_THRESHOLD: Final[float] = 0.75

#: Slot cho thấy khách đang TƯ VẤN MUA — thiếu hết thì phiên là phiên hỗ trợ (R0).
ADVISORY_SLOTS: Final[frozenset[str]] = frozenset(
    {
        "vehicle_type",
        "interest_vehicle",
        "budget_max_vnd",
        "budget_min_vnd",
        "budget_stated_vnd",
        "purpose",
        "passenger_count",
        "required_range_km",
        "habit_need_tags",
    }
)
BUDGET_SLOTS: Final[frozenset[str]] = frozenset({"budget_max_vnd", "budget_min_vnd", "budget_stated_vnd"})
#: Slot thuộc tầng Khách (không thuộc riêng cơ hội nào) — không tính khi so hai cơ hội.
CUSTOMER_LEVEL_SLOTS: Final[frozenset[str]] = frozenset({"registration_province", "home_charging"})


class AttachKind(StrEnum):
    NEW = "NEW"
    UPDATE = "UPDATE"
    SAME = "SAME"
    SUPPORT = "SUPPORT"
    AMBIGUOUS = "AMBIGUOUS"


class Decider(StrEnum):
    RULE = "RULE"
    LLM = "LLM"
    ADVISOR = "ADVISOR"


class LlmVerdict(StrEnum):
    SAME = "same"
    UPDATE = "update"
    NEW = "new"


@dataclass(frozen=True, slots=True)
class SessionFacts:
    session_id: str
    buyer_for: BuyerFor
    slots: Mapping[str, object]
    restart: bool = False

    @property
    def vehicle_type(self) -> str | None:
        value = self.slots.get("vehicle_type")
        return str(value) if value else None

    @property
    def purpose_bucket(self) -> str | None:
        value = self.slots.get("purpose_bucket")
        return str(value) if value else None

    @property
    def has_advisory_slots(self) -> bool:
        return any(_present(self.slots.get(slot)) for slot in ADVISORY_SLOTS)


@dataclass(frozen=True, slots=True)
class OpportunityView:
    opportunity_id: str
    vehicle_type: str | None
    buyer_for: BuyerFor
    slots: Mapping[str, object]
    status: str
    last_seen_at: datetime

    @property
    def purpose_bucket(self) -> str | None:
        value = self.slots.get("purpose_bucket")
        return str(value) if value else None


@dataclass(frozen=True, slots=True)
class SlotChange:
    slot: str
    value: object
    previous: object | None


@dataclass(frozen=True, slots=True)
class AttachDecision:
    kind: AttachKind
    rule_code: str
    decided_by: Decider = Decider.RULE
    target_id: str | None = None
    confidence: float = 1.0
    needs_review: bool = False
    candidates: tuple[str, ...] = ()
    changes: tuple[SlotChange, ...] = field(default_factory=tuple)


def _present(value: object) -> bool:
    return value not in (None, "", [], "__declined__")


def slot_changes(
    opportunity_slots: Mapping[str, object], session_slots: Mapping[str, object]
) -> tuple[SlotChange, ...]:
    """Slot phiên có giá trị KHÁC cơ hội (thêm mới hoặc đổi), bỏ slot tầng Khách."""

    changes = []
    for slot, value in session_slots.items():
        if slot in CUSTOMER_LEVEL_SLOTS or not _present(value):
            continue
        previous = opportunity_slots.get(slot)
        if previous != value:
            changes.append(SlotChange(slot=slot, value=value, previous=previous if _present(previous) else None))
    return tuple(sorted(changes, key=lambda change: change.slot))


def _vehicle_compatible(facts: SessionFacts, opportunity: OpportunityView) -> bool:
    return (
        facts.vehicle_type is None or opportunity.vehicle_type is None or facts.vehicle_type == opportunity.vehicle_type
    )


def _purpose_compatible(facts: SessionFacts, opportunity: OpportunityView) -> bool:
    return (
        facts.purpose_bucket is None
        or opportunity.purpose_bucket is None
        or facts.purpose_bucket == opportunity.purpose_bucket
    )


def decide(facts: SessionFacts, opportunities: Sequence[OpportunityView]) -> AttachDecision:
    """Bảng quyết định R0–R7 (plan §5.3). `opportunities` = cơ hội OPEN/DORMANT của khách."""

    if not facts.has_advisory_slots:
        return AttachDecision(kind=AttachKind.SUPPORT, rule_code="R0")
    if not opportunities:
        return AttachDecision(kind=AttachKind.NEW, rule_code="R1", changes=slot_changes({}, facts.slots))
    vehicle_matches = [item for item in opportunities if _vehicle_compatible(facts, item)]
    if not vehicle_matches:
        return AttachDecision(kind=AttachKind.NEW, rule_code="R2", changes=slot_changes({}, facts.slots))
    candidates = [item for item in vehicle_matches if item.buyer_for is facts.buyer_for]
    if not candidates:
        return AttachDecision(kind=AttachKind.NEW, rule_code="R3", changes=slot_changes({}, facts.slots))
    ordered = sorted(candidates, key=lambda item: item.last_seen_at, reverse=True)
    ambiguous = AttachDecision(
        kind=AttachKind.AMBIGUOUS,
        rule_code="R7",
        target_id=ordered[0].opportunity_id,
        candidates=tuple(item.opportunity_id for item in ordered),
    )
    if len(candidates) > 1:
        return ambiguous
    target = candidates[0]
    # Cơ hội ngủ quá lâu: một nhu cầu mua mới hay nhu cầu cũ quay lại — luật không phân biệt được.
    if target.status == "DORMANT" or not _purpose_compatible(facts, target):
        return ambiguous
    changes = slot_changes(target.slots, facts.slots)
    conflicts = {change.slot for change in changes if change.previous is not None}
    if facts.restart:
        return AttachDecision(
            kind=AttachKind.UPDATE, rule_code="R4", target_id=target.opportunity_id, confidence=0.9, changes=changes
        )
    if conflicts - BUDGET_SLOTS:
        return ambiguous
    if conflicts:
        return AttachDecision(kind=AttachKind.UPDATE, rule_code="R5", target_id=target.opportunity_id, changes=changes)
    kind = AttachKind.UPDATE if changes else AttachKind.SAME
    return AttachDecision(kind=kind, rule_code="R6", target_id=target.opportunity_id, changes=changes)


def apply_llm_verdict(
    decision: AttachDecision,
    verdict: LlmVerdict | None,
    confidence: float,
    opportunities: Sequence[OpportunityView],
    facts: SessionFacts,
    chosen_id: str | None = None,
) -> AttachDecision:
    """Áp kết luận LLM cho ca R7. `verdict=None` (LLM lỗi) = thấp tin → gắn tạm chờ TVV."""

    if decision.kind is not AttachKind.AMBIGUOUS:
        return decision
    target_id = chosen_id if chosen_id in decision.candidates else decision.target_id
    target = next((item for item in opportunities if item.opportunity_id == target_id), None)
    confident = verdict is not None and confidence >= LLM_CONFIDENCE_THRESHOLD
    if confident and verdict is LlmVerdict.NEW:
        return AttachDecision(
            kind=AttachKind.NEW,
            rule_code="R7",
            decided_by=Decider.LLM,
            confidence=confidence,
            changes=slot_changes({}, facts.slots),
        )
    changes = slot_changes(target.slots if target else {}, facts.slots)
    return AttachDecision(
        kind=AttachKind.UPDATE if changes else AttachKind.SAME,
        rule_code="R7",
        decided_by=Decider.LLM,
        target_id=target_id,
        confidence=confidence if verdict is not None else 0.0,
        needs_review=not confident,
        candidates=decision.candidates,
        changes=changes,
    )


def merge_slots(
    snapshot: Mapping[str, object],
    changes: Sequence[SlotChange],
    *,
    session_id: str,
    at: datetime,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Giá trị mới thắng nhưng GIỮ LỊCH SỬ ("850tr (trước: 700tr)") — không ghi đè im lặng."""

    merged = dict(snapshot)
    history = []
    for change in changes:
        merged[change.slot] = change.value
        history.append(
            {
                "slot": change.slot,
                "value": change.value,
                "previous": change.previous,
                "session_id": session_id,
                "at": at.isoformat(),
            }
        )
    return merged, history


__all__ = [
    "ADVISORY_SLOTS",
    "LLM_CONFIDENCE_THRESHOLD",
    "AttachDecision",
    "AttachKind",
    "Decider",
    "LlmVerdict",
    "OpportunityView",
    "SessionFacts",
    "SlotChange",
    "apply_llm_verdict",
    "decide",
    "merge_slots",
    "slot_changes",
]
