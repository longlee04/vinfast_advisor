"""DSL `eligibility_rules` — 6 test case của plan Customer 360 §5.5 + kiểm cú pháp."""

from __future__ import annotations

import pytest

from src.products.domain.eligibility_rules import Eligibility, evaluate, validate_rules

PROVINCE = {"all": [{"field": "registration_province", "in": ["HN", "HCM"]}]}


def test_d1_du_dieu_kien_kem_ly_do() -> None:
    result = evaluate(PROVINCE, {"registration_province": "HN"})
    assert result.status is Eligibility.ELIGIBLE
    assert "HN" in result.reasons[0]


def test_d2_thieu_field_la_need_info_kem_cau_hoi() -> None:
    result = evaluate(PROVINCE, {})
    assert result.status is Eligibility.NEED_INFO
    assert result.missing_fields == ("registration_province",)
    assert result.question_hints == ("Anh/chị dự định đăng ký xe ở tỉnh nào ạ?",)


def test_d3_false_thang_unknown_trong_all() -> None:
    rules = {"all": [{"field": "vehicle_type", "eq": "CAR"}, {"field": "budget_max_vnd", "gte": 500_000_000}]}
    result = evaluate(rules, {"vehicle_type": "ELECTRIC_MOTORBIKE"})
    assert result.status is Eligibility.INELIGIBLE
    assert "Loại xe" in result.failed[0]


def test_d4_true_thang_unknown_trong_any() -> None:
    rules = {"any": [{"field": "customer_group", "in": ["POLICE_MILITARY"]}, {"field": "trade_in", "eq": "YES"}]}
    assert evaluate(rules, {"trade_in": "YES"}).status is Eligibility.ELIGIBLE


def test_d5_field_la_bi_tu_choi_luc_luu_va_bi_loai_luc_danh_gia() -> None:
    rules = {"all": [{"field": "income", "gte": 1}]}
    assert validate_rules(rules) == ["$.all[0]: UNKNOWN_FIELD:income"]
    assert evaluate(rules, {"income": 5}).status is Eligibility.INVALID_RULE


def test_d6_rong_la_khong_dieu_kien() -> None:
    result = evaluate({}, {})
    assert (result.status, result.reasons) == (Eligibility.ELIGIBLE, ("Không có điều kiện",))


def test_metadata_crawler_khong_con_khop_moi_khach() -> None:
    """Trước đây `{"eligible_group": "POLICE_MILITARY", ...}` bị coi là "không điều kiện"."""

    crawler = {"source_url": "https://…", "eligible_group": "POLICE_MILITARY_AND_QUALIFIED"}
    assert evaluate(crawler, {"registration_province": "HN"}).status is Eligibility.INVALID_RULE


@pytest.mark.parametrize(
    "rules",
    [
        {"all": []},
        {"all": [{"field": "budget_max_vnd", "gte": "nhiều"}]},
        {"field": "vehicle_type", "eq": "CAR", "in": ["CAR"]},
        {"field": "registration_province", "gte": 1},
        {"field": "vehicle_type", "exists": "yes"},
        {"all": [{"field": "vehicle_type", "eq": "CAR"}], "any": []},
    ],
)
def test_cu_phap_sai_bi_bao_loi(rules: dict) -> None:
    assert validate_rules(rules)


def test_exists_va_so_sanh_so_chuoi() -> None:
    assert evaluate({"field": "home_charging", "exists": True}, {}).status is Eligibility.NEED_INFO
    assert evaluate({"field": "home_charging", "exists": False}, {}).status is Eligibility.ELIGIBLE
    assert evaluate({"field": "budget_max_vnd", "lte": 900_000_000}, {"budget_max_vnd": "850000000"}).status is (
        Eligibility.ELIGIBLE
    )
    assert evaluate({"field": "vehicle_type", "eq": "car"}, {"vehicle_type": "CAR"}).status is Eligibility.ELIGIBLE
