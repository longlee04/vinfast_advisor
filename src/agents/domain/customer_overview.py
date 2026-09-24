"""Ghép hồ sơ khách 360 từ ba lần đọc (plan Customer 360 §5.6).

Adapter đọc ĐÚNG ba câu SQL (đầu hồ sơ + cơ hội, sự kiện, phiên); mọi thứ còn lại
— nhu cầu đã có/còn thiếu/khách né, rào cản theo cơ hội, gợi ý mở lời, việc cần
làm — là hàm thuần ở đây. Câu gợi ý là MẪU CÂU tất định, không qua LLM, không chứa
con số nào không có sẵn trong dữ liệu.

THUẦN Python.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from src.agents.domain.pii import mask_phone, redact_pii
from src.agents.domain.slot_tree import slot_sequence
from src.agents.domain.values import SlotName, VehicleType

EVADED_ASK_COUNT: Final[int] = 2
#: Slot không bắt buộc — thiếu cũng không tính "còn thiếu".
_OPTIONAL_SLOTS: Final[frozenset[str]] = frozenset({SlotName.HABIT_NEED_TAGS.value})
_CUSTOMER_FIELDS: Final[tuple[str, ...]] = (
    "registration_province",
    "home_charging",
    "decision_maker",
    "payment_method",
    "current_vehicle",
    "trade_in",
)
_BARRIER_HINTS: Final[dict[str, str]] = {
    "PRICE": "Khách còn cân nhắc về giá — mở lời bằng tổng chi phí lăn bánh và ưu đãi đang áp dụng.",
    "CHARGING": "Khách lo chỗ sạc — hỏi nơi ở/nơi làm việc và giới thiệu trạm sạc gần nhất.",
    "BATTERY": "Khách lo về pin — nói rõ chính sách bảo hành và thuê/mua pin.",
    "RANGE": "Khách lo quãng đường — hỏi lộ trình thường đi để đối chiếu quãng đường thực tế.",
}
_SLOT_QUESTION: Final[dict[str, str]] = {
    "vehicle_type": "loại xe (ô tô hay xe máy điện)",
    "budget_max_vnd": "ngân sách",
    "purpose": "mục đích sử dụng",
    "passenger_count": "số người thường đi",
    "required_range_km": "quãng đường mỗi ngày",
    "home_charging": "có sạc tại nhà không",
}


@dataclass(frozen=True, slots=True)
class HeaderRow:
    customer_id: str
    display_name: str | None
    phone: str | None
    assigned_advisor_id: str | None


@dataclass(frozen=True, slots=True)
class OpportunityRow:
    opportunity_id: str
    vehicle_type: str | None
    buyer_for: str
    status: str
    stage: str
    heat_score: int
    heat_band: str
    heat_breakdown: Sequence[Mapping[str, Any]]
    slots: Mapping[str, Any]
    slot_history: Sequence[Mapping[str, Any]]
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class FactRow:
    """Một dòng view `customer_360_facts`."""

    kind: str  # INSIGHT | BOTTLENECK | BOOKING | OFFER
    ref_id: str
    opportunity_id: str | None
    session_id: str | None
    code: str
    value: str | None
    value_code: str | None
    evidence_quote: str | None
    turn_index: int | None
    status: str | None
    source: str | None
    is_current: bool
    at: datetime


@dataclass(frozen=True, slots=True)
class SessionRowIn:
    session_id: str
    started_at: datetime | None
    last_activity_at: datetime
    status: str
    ownership: str
    kind: str | None
    opportunity_id: str | None
    needs_review: bool
    decided_by: str | None
    turn_count: int | None
    ask_counts: Mapping[str, int] = field(default_factory=dict)
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class Viewer:
    """Ai đang xem — quyết định SĐT đầy đủ hay đã che, bằng chứng có qua `redact_pii` không."""

    is_admin: bool
    is_assigned_advisor: bool


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _session_status(row: SessionRowIn) -> str:
    if row.status in {"COMPLETED", "ABANDONED"}:
        return "CLOSED"
    if row.ownership == "PENDING_HANDOFF":
        return "WAITING_ADVISOR"
    return "ACTIVE"


def _format_value(slot: str, value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def missing_slots(vehicle_type: str | None, known: Mapping[str, Any]) -> list[str]:
    try:
        kind = VehicleType(vehicle_type) if vehicle_type else None
    except ValueError:
        kind = None
    return [
        slot.value
        for slot in slot_sequence(kind)
        if slot.value not in _OPTIONAL_SLOTS and known.get(slot.value) in (None, "", [], "__declined__")
    ]


def evaded_slots(missing: Sequence[str], ask_counts: Mapping[str, int]) -> list[str]:
    """Slot còn thiếu mà đã bị hỏi ≥ 2 lần — khách né câu hỏi."""

    return [slot for slot in missing if int(ask_counts.get(slot, 0)) >= EVADED_ASK_COUNT]


def _evidence(text: str | None, viewer: Viewer) -> str:
    # Admin không bao giờ thấy PII trong bằng chứng; TVV thấy câu đã che liên hệ (Phase 0).
    return redact_pii(text or "")


def opening_hint(opportunity: OpportunityRow, barriers: Sequence[Mapping[str, Any]], missing: Sequence[str]) -> str:
    """Gợi ý câu mở lời — MẪU CÂU tất định theo thứ tự ưu tiên."""

    if opportunity.stage == "TEST_DRIVE":
        return "Khách đã đặt lái thử — gọi xác nhận lịch và chuẩn bị đúng mẫu xe khách quan tâm."
    if barriers:
        return _BARRIER_HINTS.get(
            str(barriers[0]["code"]), "Khách còn một băn khoăn — hỏi lại để làm rõ trước khi tư vấn tiếp."
        )
    if opportunity.stage == "QUOTE":
        return "Khách đã xem báo giá lăn bánh — hỏi thời điểm dự định mua và hình thức thanh toán."
    if missing:
        return f"Hỏi thêm {_SLOT_QUESTION.get(missing[0], missing[0])} để đề xuất đúng xe."
    if opportunity.stage == "COMPARE":
        return "Khách đang so sánh các mẫu đã đề xuất — hỏi mẫu nào khách thích nhất và mời lái thử."
    return "Chào khách, nhắc lại nhu cầu đã trao đổi và hỏi khách cần hỗ trợ gì thêm."


def next_actions(
    opportunity: OpportunityRow,
    barriers: Sequence[Mapping[str, Any]],
    missing: Sequence[str],
    sessions: Sequence[SessionRowIn],
    bookings: Sequence[FactRow],
    has_phone: bool,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if any(row.needs_review for row in sessions):
        actions.append({"code": "REVIEW_ATTACH", "label": "Xác nhận phiên thuộc nhu cầu nào (Tách/Gộp)"})
    if any(_session_status(row) == "WAITING_ADVISOR" for row in sessions):
        actions.append({"code": "TAKE_OVER", "label": "Khách đang chờ tư vấn viên — tiếp quản ngay"})
    if any(row.status == "REQUESTED" for row in bookings):
        actions.append({"code": "CONFIRM_TEST_DRIVE", "label": "Xác nhận lịch lái thử"})
    if opportunity.heat_band == "HOT" and has_phone:
        actions.append({"code": "CALL_BACK", "label": "Gọi lại khách (đang nóng)"})
    for barrier in barriers[:2]:
        actions.append({"code": f"RESOLVE_{barrier['code']}", "label": f"Xử lý băn khoăn: {barrier['code']}"})
    if missing:
        actions.append(
            {
                "code": "ASK_MISSING",
                "label": "Hỏi thêm: " + ", ".join(_SLOT_QUESTION.get(slot, slot) for slot in missing[:3]),
            }
        )
    return actions


def build_overview(
    header: HeaderRow,
    opportunities: Sequence[OpportunityRow],
    facts: Sequence[FactRow],
    sessions: Sequence[SessionRowIn],
    viewer: Viewer,
) -> dict[str, Any]:
    """Payload đúng hợp đồng `CustomerOverview` (plan §6 Phase 4 mục 5)."""

    insights = [fact for fact in facts if fact.kind == "INSIGHT"]
    bookings = [fact for fact in facts if fact.kind == "BOOKING"]
    sessions_by_opp: dict[str | None, list[SessionRowIn]] = defaultdict(list)
    for row in sessions:
        sessions_by_opp[row.opportunity_id].append(row)

    def field_value(items: Sequence[FactRow]) -> dict[str, Any] | None:
        ordered = sorted(items, key=lambda fact: fact.at)
        current = next((fact for fact in reversed(ordered) if fact.is_current), None)
        if current is None:
            return None
        return {
            "value": current.value or "",
            "value_code": current.value_code,
            "source": current.source or "LLM",
            "evidence_quote": _evidence(current.evidence_quote, viewer) or None,
            "turn_index": current.turn_index,
            "at": current.at.isoformat(),
            "history": [
                {"value": fact.value or "", "at": fact.at.isoformat()} for fact in ordered if not fact.is_current
            ],
        }

    customer_fields: dict[str, Any] = {}
    for name in _CUSTOMER_FIELDS:
        value = field_value([fact for fact in insights if fact.code == name and fact.opportunity_id is None])
        if value is not None:
            customer_fields[name] = value

    opportunity_payloads = []
    for opportunity in opportunities:
        opp_sessions = sessions_by_opp.get(opportunity.opportunity_id, [])
        barriers = [
            {
                "code": fact.code,
                "source": "BOTTLENECK",
                "evidence_quote": _evidence(fact.evidence_quote, viewer),
                "turn_index": fact.turn_index,
                "session_id": fact.session_id,
                "status": fact.status or "",
            }
            for fact in facts
            if fact.kind == "BOTTLENECK" and fact.opportunity_id == opportunity.opportunity_id
        ] + [
            {
                "code": "OTHER",
                "source": "INSIGHT",
                "evidence_quote": _evidence(fact.evidence_quote, viewer),
                "turn_index": fact.turn_index,
                "session_id": fact.session_id,
                "status": "CURRENT",
            }
            for fact in insights
            if fact.code == "other_concern" and fact.opportunity_id == opportunity.opportunity_id and fact.is_current
        ]
        history_by_slot: dict[str, list[dict[str, str]]] = defaultdict(list)
        for entry in opportunity.slot_history:
            if entry.get("previous") not in (None, ""):
                history_by_slot[str(entry["slot"])].append(
                    {"value": _format_value(str(entry["slot"]), entry["previous"]), "at": str(entry.get("at", ""))}
                )
        known = [
            {"slot": slot, "value": _format_value(slot, value), "history": history_by_slot.get(slot, [])}
            for slot, value in opportunity.slots.items()
            if slot != "purpose_bucket" and value not in (None, "", [], "__declined__")
        ]
        missing = missing_slots(opportunity.vehicle_type, opportunity.slots)
        asked: dict[str, int] = defaultdict(int)
        for row in opp_sessions:
            for slot, count in (row.ask_counts or {}).items():
                asked[slot] = max(asked[slot], int(count))
        evaded = evaded_slots(missing, asked)
        opp_insights = [
            {
                "insight_id": fact.ref_id,
                "field": fact.code,
                "value": fact.value or "",
                "value_code": fact.value_code,
                "source": fact.source or "LLM",
                "evidence_quote": _evidence(fact.evidence_quote, viewer) or None,
                "turn_index": fact.turn_index,
                "at": fact.at.isoformat(),
                "history": [],
            }
            for fact in insights
            if fact.opportunity_id == opportunity.opportunity_id and fact.is_current and fact.code != "other_concern"
        ]
        opportunity_payloads.append(
            {
                "opportunity_id": opportunity.opportunity_id,
                "vehicle_type": opportunity.vehicle_type,
                "buyer_for": opportunity.buyer_for,
                "status": opportunity.status,
                "stage": opportunity.stage,
                "heat_score": opportunity.heat_score,
                "heat_band": opportunity.heat_band,
                "heat_breakdown": list(opportunity.heat_breakdown),
                "needs": {"known": known, "missing": missing, "evaded": evaded},
                "barriers": barriers,
                "insights": opp_insights,
                "offers": [
                    {
                        "offer_id": fact.ref_id,
                        "promotion_code": fact.code,
                        "status": fact.status or "",
                        "discount_vnd": int(fact.value) if fact.value and fact.value.isdigit() else None,
                        "eligibility": fact.value_code,
                        "at": fact.at.isoformat(),
                    }
                    for fact in facts
                    if fact.kind == "OFFER" and fact.opportunity_id == opportunity.opportunity_id
                ],
                "opening_hint": opening_hint(opportunity, barriers, missing),
                "next_actions": next_actions(
                    opportunity, barriers, missing, opp_sessions, bookings, bool(header.phone)
                ),
            }
        )

    open_opportunities = [item for item in opportunities if item.status == "OPEN"] or list(opportunities)
    hottest = max(open_opportunities, key=lambda item: item.heat_score, default=None)
    show_full_phone = viewer.is_assigned_advisor and not viewer.is_admin
    last_seen = max((row.last_activity_at for row in sessions), default=None)
    return {
        "customer": {
            "customer_id": header.customer_id,
            "display_name": header.display_name,
            "phone_masked": mask_phone(header.phone) if header.phone else None,
            **({"phone": header.phone} if show_full_phone and header.phone else {}),
            "assigned_advisor_id": header.assigned_advisor_id,
            "heat_band": hottest.heat_band if hottest else None,
            "heat_score": hottest.heat_score if hottest else None,
            "sessions_count": len(sessions),
            "last_seen_at": _iso(last_seen),
            "fields": customer_fields,
        },
        "opportunities": opportunity_payloads,
        "sessions": [
            {
                "session_id": row.session_id,
                "started_at": _iso(row.started_at),
                "last_activity_at": row.last_activity_at.isoformat(),
                "status": _session_status(row),
                "ownership": row.ownership,
                "kind": row.kind or "UNASSIGNED",
                "opportunity_id": row.opportunity_id,
                "needs_review": row.needs_review,
                "decided_by": row.decided_by,
                "turn_count": row.turn_count,
                "summary_excerpt": redact_pii(row.summary) if row.summary else None,
            }
            for row in sessions
        ],
        "test_drives": [
            {
                "booking_id": fact.ref_id,
                "vehicle_id": fact.value or "",
                "showroom": fact.evidence_quote or "",
                "scheduled_at": fact.at.isoformat(),
                "status": fact.status or "",
            }
            for fact in bookings
        ],
    }


__all__ = [
    "FactRow",
    "HeaderRow",
    "OpportunityRow",
    "SessionRowIn",
    "Viewer",
    "build_overview",
    "next_actions",
    "opening_hint",
]
