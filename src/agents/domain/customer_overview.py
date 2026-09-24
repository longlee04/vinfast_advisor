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
    #: Khách tự khai (plan §19) — như SĐT đầy đủ, chỉ TVV phụ trách được xem.
    address: str | None = None


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
    #: Bản tóm tắt đầy đủ (`summary` là đoạn trích 280 ký tự cho danh sách phiên).
    summary_full: str | None = None
    last_quote_sent_at: datetime | None = None
    chosen_vehicle_id: str | None = None
    #: Thẻ đề xuất của lượt GẦN NHẤT có đề xuất (`conversation_turn_outcomes.recommendations`).
    latest_recommendations: Sequence[Mapping[str, Any]] = ()
    first_recommendation_at: datetime | None = None
    #: Câu khách hỏi về tính năng (`pending_feature_mentions.raw_mention`), cũ → mới.
    feature_mentions: Sequence[str] = ()


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


def opening_basis(
    opportunity: OpportunityRow, barriers: Sequence[Mapping[str, Any]], missing: Sequence[str]
) -> dict[str, str]:
    """Gợi ý mở lời dựa trên gì — `{kind, code?}`; frontend dựng câu "Dựa trên …" bằng nhãn của nó.

    CÙNG thứ tự ưu tiên với `opening_hint` (hai hàm đọc chung `_opening`), nên lý do
    không bao giờ lệch khỏi câu gợi ý đang hiện.
    """

    return _opening(opportunity, barriers, missing)[1]


def opening_hint(opportunity: OpportunityRow, barriers: Sequence[Mapping[str, Any]], missing: Sequence[str]) -> str:
    """Gợi ý câu mở lời — MẪU CÂU tất định theo thứ tự ưu tiên."""

    return _opening(opportunity, barriers, missing)[0]


def _opening(
    opportunity: OpportunityRow, barriers: Sequence[Mapping[str, Any]], missing: Sequence[str]
) -> tuple[str, dict[str, str]]:
    if opportunity.stage == "TEST_DRIVE":
        return (
            "Khách đã đặt lái thử — gọi xác nhận lịch và chuẩn bị đúng mẫu xe khách quan tâm.",
            {"kind": "TEST_DRIVE"},
        )
    if barriers:
        code = str(barriers[0]["code"])
        return (
            _BARRIER_HINTS.get(code, "Khách còn một băn khoăn — hỏi lại để làm rõ trước khi tư vấn tiếp."),
            {"kind": "BARRIER", "code": code},
        )
    if opportunity.stage == "QUOTE":
        return (
            "Khách đã xem báo giá lăn bánh — hỏi thời điểm dự định mua và hình thức thanh toán.",
            {"kind": "QUOTE"},
        )
    if missing:
        return (
            f"Hỏi thêm {_SLOT_QUESTION.get(missing[0], missing[0])} để đề xuất đúng xe.",
            {"kind": "MISSING", "code": missing[0]},
        )
    if opportunity.stage == "COMPARE":
        return (
            "Khách đang so sánh các mẫu đã đề xuất — hỏi mẫu nào khách thích nhất và mời lái thử.",
            {"kind": "COMPARE"},
        )
    return "Chào khách, nhắc lại nhu cầu đã trao đổi và hỏi khách cần hỗ trợ gì thêm.", {"kind": "DEFAULT"}


@dataclass(frozen=True, slots=True)
class ActionSignals:
    """Tín hiệu đủ để quyết "việc nên làm" — dựng được từ hồ sơ (3 câu SQL) LẪN từ một dòng danh sách.

    Hai màn đọc chung `actions_from_signals`, nên "Việc nên làm" trên danh sách luôn là
    việc đầu tiên trong "Việc cần làm" của hồ sơ.
    """

    heat_band: str
    needs_review: bool = False
    waiting: bool = False
    booking_requested: bool = False
    has_phone: bool = False
    barrier_codes: Sequence[str] = ()
    missing: Sequence[str] = ()


def actions_from_signals(signals: ActionSignals) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if signals.needs_review:
        actions.append({"code": "REVIEW_ATTACH", "label": "Xác nhận phiên thuộc nhu cầu nào (Tách/Gộp)"})
    if signals.waiting:
        actions.append({"code": "TAKE_OVER", "label": "Khách đang chờ tư vấn viên — tiếp quản ngay"})
    if signals.booking_requested:
        actions.append({"code": "CONFIRM_TEST_DRIVE", "label": "Xác nhận lịch lái thử"})
    if signals.heat_band == "HOT" and signals.has_phone:
        actions.append({"code": "CALL_BACK", "label": "Gọi lại khách (đang nóng)"})
    for code in signals.barrier_codes[:2]:
        actions.append({"code": f"RESOLVE_{code}", "label": f"Xử lý băn khoăn: {code}"})
    if signals.missing:
        actions.append(
            {
                "code": "ASK_MISSING",
                "label": "Hỏi thêm: " + ", ".join(_SLOT_QUESTION.get(slot, slot) for slot in signals.missing[:3]),
            }
        )
    return actions


def next_actions(
    opportunity: OpportunityRow,
    barriers: Sequence[Mapping[str, Any]],
    missing: Sequence[str],
    sessions: Sequence[SessionRowIn],
    bookings: Sequence[FactRow],
    has_phone: bool,
) -> list[dict[str, str]]:
    return actions_from_signals(
        ActionSignals(
            heat_band=opportunity.heat_band,
            needs_review=any(row.needs_review for row in sessions),
            waiting=any(_session_status(row) == "WAITING_ADVISOR" for row in sessions),
            booking_requested=any(row.status == "REQUESTED" for row in bookings),
            has_phone=has_phone,
            barrier_codes=[str(barrier["code"]) for barrier in barriers],
            missing=missing,
        )
    )


def stage_history(
    opportunity: OpportunityRow, sessions: Sequence[SessionRowIn], bookings: Sequence[FactRow]
) -> list[dict[str, Any]]:
    """Mốc ĐẦU TIÊN của từng giai đoạn mà dữ liệu chứng minh được — không có bằng chứng thì không có mốc.

    - Tìm hiểu: phiên đầu tiên của cơ hội bắt đầu.
    - So sánh: lượt đầu tiên bot đưa thẻ đề xuất.
    - Báo giá: lần gần nhất gửi báo giá lăn bánh (`last_quote_sent_at` chỉ giữ lần cuối).
    - Lái thử: lịch lái thử sớm nhất của khách (ghi chú = trạng thái lịch).
    - Chốt: chỉ khi cơ hội `WON` — dùng `last_seen_at` làm mốc.
    """

    def earliest(values: Sequence[datetime | None]) -> datetime | None:
        present = [value for value in values if value is not None]
        return min(present) if present else None

    marks: list[dict[str, Any]] = []
    discover = earliest([row.started_at for row in sessions])
    if discover:
        marks.append({"stage": "DISCOVER", "at": discover.isoformat()})
    compare = earliest([row.first_recommendation_at for row in sessions])
    if compare:
        marks.append({"stage": "COMPARE", "at": compare.isoformat()})
    quote = earliest([row.last_quote_sent_at for row in sessions])
    if quote:
        marks.append({"stage": "QUOTE", "at": quote.isoformat()})
    live_bookings = sorted((row for row in bookings if row.status != "CANCELLED"), key=lambda row: row.at)
    if live_bookings:
        first = live_bookings[0]
        marks.append({"stage": "TEST_DRIVE", "at": first.at.isoformat(), "note": first.status or None})
    if opportunity.status == "WON":
        marks.append({"stage": "CLOSE", "at": opportunity.last_seen_at.isoformat()})
    return marks


#: Số xe tối đa trong khối "Xe quan tâm" — hơn thế là danh sách đề xuất, không còn là "quan tâm".
MAX_VEHICLES_OF_INTEREST: Final[int] = 3


def vehicles_of_interest(sessions: Sequence[SessionRowIn]) -> list[dict[str, Any]]:
    """Xe khách quan tâm, lấy từ thẻ đề xuất GẦN NHẤT và xe khách đã chốt trong phiên.

    Tên xe chép nguyên từ thẻ đề xuất đã gửi khách (không tra/sinh lại). Không có số tiền
    nào ở đây: giá báo lăn bánh không lưu theo xe, nên chỉ ghi THỜI ĐIỂM đã gửi báo giá
    cho xe khách chốt. Câu hỏi tính năng gắn vào xe đứng đầu — dữ liệu không nói khách hỏi
    cho xe nào, nên chỉ gắn một chỗ thay vì nhân bản cho mọi xe.
    """

    latest = max(
        (row for row in sessions if row.latest_recommendations),
        key=lambda row: row.last_activity_at,
        default=None,
    )
    chosen_row = max(
        (row for row in sessions if row.chosen_vehicle_id),
        key=lambda row: row.last_activity_at,
        default=None,
    )
    names: dict[str, str] = {}
    for row in sessions:
        for card in row.latest_recommendations:
            if card.get("vehicle_id") and card.get("display_name"):
                names[str(card["vehicle_id"])] = str(card["display_name"])

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    if chosen_row is not None and chosen_row.chosen_vehicle_id in names:
        vehicle_id = str(chosen_row.chosen_vehicle_id)
        seen.add(vehicle_id)
        items.append(
            {
                "vehicle_id": vehicle_id,
                "name": names[vehicle_id],
                "role": "CHOSEN",
                "rank": None,
                "quote_sent_at": _iso(chosen_row.last_quote_sent_at),
            }
        )
    if latest is not None:
        for card in sorted(latest.latest_recommendations, key=lambda item: int(item.get("rank") or 99)):
            vehicle_id = str(card.get("vehicle_id") or "")
            if not vehicle_id or vehicle_id in seen or not card.get("display_name"):
                continue
            seen.add(vehicle_id)
            items.append(
                {
                    "vehicle_id": vehicle_id,
                    "name": str(card["display_name"]),
                    "role": "RECOMMENDED",
                    "rank": int(card["rank"]) if card.get("rank") is not None else None,
                    "quote_sent_at": None,
                }
            )
    items = items[:MAX_VEHICLES_OF_INTEREST]
    mentions = list(dict.fromkeys(redact_pii(text) for row in sessions for text in row.feature_mentions if text))
    for index, item in enumerate(items):
        item["asked_features"] = mentions[:5] if index == 0 else []
    return items


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
                "at": fact.at.isoformat(),
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
                "at": fact.at.isoformat(),
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
                "needs": {
                    "known": known,
                    "missing": missing,
                    "evaded": evaded,
                    # Cùng danh sách `evaded`, kèm số lần bot đã hỏi — hiện "Khách né · hỏi N lần".
                    "evaded_detail": [{"slot": slot, "ask_count": int(asked[slot])} for slot in evaded],
                },
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
                "opening_hint_basis": opening_basis(opportunity, barriers, missing),
                "stage_history": stage_history(opportunity, opp_sessions, bookings),
                "vehicles_of_interest": vehicles_of_interest(opp_sessions),
                "next_actions": next_actions(
                    opportunity, barriers, missing, opp_sessions, bookings, bool(header.phone)
                ),
            }
        )

    open_opportunities = [item for item in opportunities if item.status == "OPEN"] or list(opportunities)
    hottest = max(open_opportunities, key=lambda item: item.heat_score, default=None)
    show_full_phone = viewer.is_assigned_advisor and not viewer.is_admin
    last_seen = max((row.last_activity_at for row in sessions), default=None)
    latest_summary = next((row.summary_full for row in sessions if row.summary_full), None)
    return {
        "customer": {
            "customer_id": header.customer_id,
            "display_name": header.display_name,
            "phone_masked": mask_phone(header.phone) if header.phone else None,
            **({"phone": header.phone} if show_full_phone and header.phone else {}),
            **({"address": header.address} if show_full_phone and header.address else {}),
            "assigned_advisor_id": header.assigned_advisor_id,
            "heat_band": hottest.heat_band if hottest else None,
            "heat_score": hottest.heat_score if hottest else None,
            "sessions_count": len(sessions),
            "last_seen_at": _iso(last_seen),
            "fields": customer_fields,
            # Tóm tắt ĐẦY ĐỦ của phiên mới nhất có tóm tắt (`sessions[].summary_excerpt` bị cắt 280 ký tự).
            "latest_summary": redact_pii(latest_summary) if latest_summary else None,
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
    "ActionSignals",
    "Viewer",
    "actions_from_signals",
    "build_overview",
    "next_actions",
    "opening_basis",
    "opening_hint",
    "stage_history",
    "vehicles_of_interest",
]
