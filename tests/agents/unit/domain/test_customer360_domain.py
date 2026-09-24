"""Heat score (3 ví dụ tính tay §5.2), giai đoạn bán hàng, buyer_for, insight, ghép hồ sơ."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.agents.domain.buyer_for import BuyerFor, detect_buyer_for
from src.agents.domain.customer_insight import (
    CurrentInsight,
    InsightField,
    RejectReason,
    SaveAction,
    insight_scope,
    plan_save,
    validate_candidate,
)
from src.agents.domain.customer_overview import (
    FactRow,
    HeaderRow,
    OpportunityRow,
    SessionRowIn,
    Viewer,
    build_overview,
)
from src.agents.domain.heat_score import HeatBand, HeatSignals, band_for, compute_heat
from src.agents.domain.sales_stage import SalesStage, StageSignals, derive_stage

NOW = datetime(2026, 9, 24, tzinfo=UTC)


# ---------------------------------------------------------------- heat score


def test_heat_vi_du_a_nong() -> None:
    result = compute_heat(
        HeatSignals(
            stage=SalesStage.TEST_DRIVE,
            purchase_timeframe="WITHIN_1_MONTH",
            has_phone=True,
            budget_stated=True,
            days_since_seen=1,
        )
    )
    assert (result.score, result.band) == (70, HeatBand.HOT)
    assert [part.code for part in result.breakdown] == ["H1", "H2", "H3", "H6"]


def test_heat_vi_du_b_am() -> None:
    result = compute_heat(
        HeatSignals(stage=SalesStage.QUOTE, sessions_14d=2, budget_stated=True, payment_asked=True, days_since_seen=5)
    )
    assert (result.score, result.band) == (35, HeatBand.WARM)


def test_heat_vi_du_c_lanh_kep_ve_0() -> None:
    result = compute_heat(HeatSignals(stage=SalesStage.COMPARE, budget_stated=True, evaded_slots=2, days_since_seen=10))
    assert (result.score, result.band) == (0, HeatBand.COLD)


def test_heat_dormant_kep_tran_va_nguong() -> None:
    result = compute_heat(HeatSignals(stage=SalesStage.CLOSE, purchase_timeframe="WITHIN_1_MONTH", days_since_seen=45))
    assert result.dormant and result.score == 15
    assert (band_for(60), band_for(59), band_for(30), band_for(29)) == (
        HeatBand.HOT,
        HeatBand.WARM,
        HeatBand.WARM,
        HeatBand.COLD,
    )
    evaded = compute_heat(HeatSignals(stage=SalesStage.CLOSE, evaded_slots=5))
    assert next(part.points for part in evaded.breakdown if part.code == "H8") == -10


# ---------------------------------------------------------------- sales stage


def test_giai_doan_lay_bac_cao_nhat_va_khong_lui() -> None:
    assert derive_stage(StageSignals()) is SalesStage.DISCOVER
    assert derive_stage(StageSignals(core_stages=frozenset({"COSTING", "RECOMMENDED"}))) is SalesStage.QUOTE
    # SCHEDULING chưa có lịch thật chỉ là QUOTE (G6); có lịch mới là TEST_DRIVE.
    assert derive_stage(StageSignals(core_stages=frozenset({"SCHEDULING"}))) is SalesStage.QUOTE
    assert derive_stage(StageSignals(has_test_drive=True)) is SalesStage.TEST_DRIVE
    assert derive_stage(StageSignals(), current=SalesStage.QUOTE) is SalesStage.QUOTE
    assert derive_stage(StageSignals(core_stages=frozenset({"HANDED_OFF"}))) is SalesStage.DISCOVER


# ---------------------------------------------------------------- buyer_for


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mua xe chở con đi học", BuyerFor.SELF),
        ("tìm thêm ô tô nhỏ cho con gái đi làm", BuyerFor.FAMILY),
        ("báo giá cho con VF 5", BuyerFor.SELF),
        ("tư vấn xe cho gia đình 5 người", BuyerFor.SELF),
        ("tư vấn cho em xe điện", BuyerFor.SELF),
        ("xe cho công ty chạy dịch vụ", BuyerFor.COMPANY),
        ("công ty em muốn mua 3 xe", BuyerFor.COMPANY),
        ("mua cho vo", BuyerFor.FAMILY),
        ("mua cho bạn thân", BuyerFor.OTHER),
    ],
)
def test_buyer_for(text: str, expected: BuyerFor) -> None:
    assert detect_buyer_for([text]) is expected


# ---------------------------------------------------------------- insight

TURNS = {3: "Chắc tháng này em chốt, trả góp qua ngân hàng", 5: "Nhà em ở chung cư"}


def _raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "field": "purchase_timeframe",
        "value": "trong tháng này",
        "value_code": "WITHIN_1_MONTH",
        "evidence_quote": "tháng này em chốt",
        "turn_index": 3,
        "confidence": 0.9,
    }
    raw.update(overrides)
    return raw


def test_insight_hop_le_va_bang_chung_go_khong_dau_van_khop() -> None:
    candidate = validate_candidate(_raw(evidence_quote="thang nay em chot"), TURNS)
    assert not isinstance(candidate, RejectReason)
    assert candidate.field is InsightField.PURCHASE_TIMEFRAME and candidate.turn_index == 3


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"field": "marital_status"}, RejectReason.UNKNOWN_FIELD),
        ({"field": "registration_province"}, RejectReason.UNKNOWN_FIELD),
        ({"turn_index": 9}, RejectReason.UNKNOWN_TURN),
        ({"evidence_quote": "em đã có gia đình"}, RejectReason.NO_EVIDENCE),
        ({"evidence_quote": "tháng này em chốt", "turn_index": 5}, RejectReason.NO_EVIDENCE),
        ({"value_code": "TOMORROW"}, RejectReason.BAD_VALUE_CODE),
        (
            {"field": "payment_method", "value_code": "CASH", "evidence_quote": "trả góp qua ngân hàng"},
            RejectReason.LEXICON_MISMATCH,
        ),
        ({"confidence": 0.3}, RejectReason.LOW_CONFIDENCE),
    ],
)
def test_insight_bi_loai_khi_suy_dien(overrides: dict[str, object], reason: RejectReason) -> None:
    assert validate_candidate(_raw(**overrides), TURNS) is reason


def test_mau_thuan_thi_supersede_trung_thi_bo_qua_da_tri_thi_them() -> None:
    current = [CurrentInsight("i1", InsightField.PAYMENT_METHOD, None, "trả thẳng", "CASH")]
    assert (
        plan_save(InsightField.PAYMENT_METHOD, "trả góp", "INSTALLMENT", None, current).action is SaveAction.SUPERSEDE
    )
    assert plan_save(InsightField.PAYMENT_METHOD, "tiền mặt", "CASH", None, current).action is SaveAction.SKIP_DUPLICATE
    assert plan_save(InsightField.PAYMENT_METHOD, "trả góp", "INSTALLMENT", None, []).action is SaveAction.INSERT
    brands = [CurrentInsight("i2", InsightField.COMPETITOR_BRAND, "O1", "BYD", None)]
    assert plan_save(InsightField.COMPETITOR_BRAND, "Tesla", None, "O1", brands).action is SaveAction.INSERT
    assert insight_scope(InsightField.PAYMENT_METHOD, "O1") is None
    assert insight_scope(InsightField.PURCHASE_TIMEFRAME, "O1") == "O1"


# ---------------------------------------------------------------- overview


def _overview(viewer: Viewer) -> dict:
    opportunity = OpportunityRow(
        opportunity_id="O1",
        vehicle_type="CAR",
        buyer_for="SELF",
        status="OPEN",
        stage="QUOTE",
        heat_score=65,
        heat_band="HOT",
        heat_breakdown=[{"code": "H1", "points": 25, "detail": "QUOTE"}],
        slots={"vehicle_type": "CAR", "budget_max_vnd": 850_000_000, "purpose_bucket": "FAMILY"},
        slot_history=[{"slot": "budget_max_vnd", "value": 850_000_000, "previous": 700_000_000, "at": "2026-09-20"}],
        last_seen_at=NOW,
    )
    facts = [
        FactRow(
            "BOTTLENECK",
            "b1",
            "O1",
            "S1",
            "PRICE",
            None,
            None,
            "đắt quá, gọi 0912345678",
            4,
            "CORRECT",
            "BOTTLENECK",
            True,
            NOW,
        ),
        FactRow(
            "INSIGHT",
            "i0",
            None,
            "S1",
            "payment_method",
            "trả thẳng",
            "CASH",
            "trả thẳng",
            2,
            None,
            "LLM",
            False,
            NOW - timedelta(days=3),
        ),
        FactRow(
            "INSIGHT",
            "i1",
            None,
            "S1",
            "payment_method",
            "trả góp",
            "INSTALLMENT",
            "trả góp",
            6,
            None,
            "LLM",
            True,
            NOW,
        ),
    ]
    sessions = [
        SessionRowIn(
            "S1", NOW, NOW, "ACTIVE", "PENDING_HANDOFF", "SALES", "O1", True, "LLM", 6, {"passenger_count": 2}
        ),
    ]
    header = HeaderRow("cust-1", "Nguyễn An", "0912345678", "adv-1")
    return build_overview(header, [opportunity], facts, sessions, viewer)


def test_ho_so_tvv_phu_trach_thay_sdt_day_du_va_can_bang_chung_da_che() -> None:
    payload = _overview(Viewer(is_admin=False, is_assigned_advisor=True))

    assert payload["customer"]["phone"] == "0912345678"
    assert payload["customer"]["heat_band"] == "HOT"
    [opp] = payload["opportunities"]
    assert opp["needs"]["missing"] == ["passenger_count", "required_range_km", "home_charging", "purpose"]
    assert opp["needs"]["evaded"] == ["passenger_count"]
    assert "purpose_bucket" not in {item["slot"] for item in opp["needs"]["known"]}
    budget = next(item for item in opp["needs"]["known"] if item["slot"] == "budget_max_vnd")
    assert budget["history"][0]["value"] == "700000000"
    assert opp["barriers"][0]["evidence_quote"] == "đắt quá, gọi [SĐT]"
    assert opp["opening_hint"].startswith("Khách còn cân nhắc về giá")
    codes = [action["code"] for action in opp["next_actions"]]
    assert codes[:2] == ["REVIEW_ATTACH", "TAKE_OVER"] and "CALL_BACK" in codes
    payment = payload["customer"]["fields"]["payment_method"]
    assert payment["value_code"] == "INSTALLMENT" and payment["history"][0]["value"] == "trả thẳng"
    assert payload["sessions"][0]["status"] == "WAITING_ADVISOR"


def test_ho_so_admin_chi_thay_sdt_da_che() -> None:
    payload = _overview(Viewer(is_admin=True, is_assigned_advisor=False))

    assert "phone" not in payload["customer"]
    assert payload["customer"]["phone_masked"] == "0912***678"
