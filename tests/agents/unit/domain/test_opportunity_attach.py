"""Luật gộp/tách cơ hội R0–R7 — 6 test case bắt buộc của plan Customer 360 §5.3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.domain.buyer_for import BuyerFor
from src.agents.domain.opportunity_attach import (
    AttachKind,
    Decider,
    LlmVerdict,
    OpportunityView,
    SessionFacts,
    apply_llm_verdict,
    decide,
    merge_slots,
)

NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _opp(opportunity_id: str = "O1", **overrides: object) -> OpportunityView:
    values: dict[str, object] = {
        "opportunity_id": opportunity_id,
        "vehicle_type": "CAR",
        "buyer_for": BuyerFor.SELF,
        "slots": {"vehicle_type": "CAR", "purpose_bucket": "FAMILY", "budget_max_vnd": 700_000_000},
        "status": "OPEN",
        "last_seen_at": NOW - timedelta(days=2),
    }
    values.update(overrides)
    return OpportunityView(**values)  # type: ignore[arg-type]


def _facts(slots: dict[str, object], *, buyer: BuyerFor = BuyerFor.SELF, restart: bool = False) -> SessionFacts:
    return SessionFacts(session_id="S2", buyer_for=buyer, slots=slots, restart=restart)


def test_tc1_cung_xe_doi_ngan_sach_la_cap_nhat_co_luu_vet() -> None:
    decision = decide(
        _facts({"vehicle_type": "CAR", "purpose_bucket": "FAMILY", "budget_max_vnd": 850_000_000}), [_opp()]
    )

    assert (decision.kind, decision.rule_code, decision.target_id) == (AttachKind.UPDATE, "R5", "O1")
    assert decision.decided_by is Decider.RULE and decision.confidence == 1.0
    [change] = decision.changes
    assert (change.slot, change.value, change.previous) == ("budget_max_vnd", 850_000_000, 700_000_000)
    merged, history = merge_slots(_opp().slots, decision.changes, session_id="S2", at=NOW)
    assert merged["budget_max_vnd"] == 850_000_000
    assert history[0]["previous"] == 700_000_000


def test_tc2_o_to_sang_xe_may_la_co_hoi_moi() -> None:
    decision = decide(_facts({"vehicle_type": "ELECTRIC_MOTORBIKE", "budget_max_vnd": 30_000_000}), [_opp()])

    assert (decision.kind, decision.rule_code, decision.target_id) == (AttachKind.NEW, "R2", None)


def test_tc3_mua_cho_con_la_co_hoi_moi() -> None:
    decision = decide(_facts({"vehicle_type": "CAR"}, buyer=BuyerFor.FAMILY), [_opp()])

    assert (decision.kind, decision.rule_code) == (AttachKind.NEW, "R3")


def test_tc4_phien_chi_hoi_bao_hanh_khong_tao_co_hoi() -> None:
    decision = decide(_facts({"registration_province": "HN"}), [_opp()])

    assert (decision.kind, decision.rule_code, decision.target_id) == (AttachKind.SUPPORT, "R0", None)


def test_tc5_tu_van_lai_tu_dau_cap_nhat_co_hoi_cu_giu_lich_su() -> None:
    decision = decide(
        _facts({"vehicle_type": "CAR", "purpose_bucket": "FAMILY", "budget_max_vnd": 1_000_000_000}, restart=True),
        [_opp()],
    )

    assert (decision.kind, decision.rule_code, decision.target_id, decision.confidence) == (
        AttachKind.UPDATE,
        "R4",
        "O1",
        0.9,
    )
    assert decision.changes[0].previous == 700_000_000


def test_tc6_mo_ho_can_tvv_quyet() -> None:
    dormant = _opp(status="DORMANT", last_seen_at=NOW - timedelta(days=40))
    facts = _facts({"vehicle_type": "CAR", "budget_max_vnd": 1_200_000_000})

    decision = decide(facts, [dormant])
    assert (decision.kind, decision.rule_code, decision.candidates) == (AttachKind.AMBIGUOUS, "R7", ("O1",))

    low = apply_llm_verdict(decision, LlmVerdict.UPDATE, 0.55, [dormant], facts)
    assert (low.kind, low.target_id, low.decided_by, low.needs_review) == (AttachKind.UPDATE, "O1", Decider.LLM, True)

    failed = apply_llm_verdict(decision, None, 0.0, [dormant], facts)
    assert failed.needs_review and failed.confidence == 0.0

    confident_new = apply_llm_verdict(decision, LlmVerdict.NEW, 0.9, [dormant], facts)
    assert (confident_new.kind, confident_new.needs_review) == (AttachKind.NEW, False)


def test_khach_moi_va_nhieu_ung_vien() -> None:
    assert decide(_facts({"vehicle_type": "CAR"}), []).rule_code == "R1"
    two = [_opp("O1"), _opp("O2", last_seen_at=NOW)]
    decision = decide(_facts({"vehicle_type": "CAR"}), two)
    assert decision.kind is AttachKind.AMBIGUOUS and decision.target_id == "O2"


def test_doi_slot_khong_phai_ngan_sach_la_mo_ho_con_them_slot_moi_la_cap_nhat() -> None:
    opp = _opp(slots={"vehicle_type": "CAR", "purpose_bucket": "FAMILY", "passenger_count": 4})
    assert decide(_facts({"vehicle_type": "CAR", "passenger_count": 7}), [opp]).kind is AttachKind.AMBIGUOUS
    added = decide(_facts({"vehicle_type": "CAR", "required_range_km": 80}), [opp])
    assert (added.kind, added.rule_code) == (AttachKind.UPDATE, "R6")
    same = decide(_facts({"vehicle_type": "CAR", "passenger_count": 4}), [opp])
    assert (same.kind, same.rule_code) == (AttachKind.SAME, "R6")
