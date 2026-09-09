"""Bản dựng tay được ghép từ MẤY claim, và chọn claim nào.

Bản cũ cắt cứng `[:2]`:

    selected_claims = (...)[:2]

Xe có 9 tính năng đã xác minh vẫn chỉ được nói **hai** điều. Đo trên prod
2026-08-28, khách nhận đúng một câu như thế và không có con số nào:

> "VinFast VF 5 All New thuộc đúng dòng xe Quý khách đang tìm, có tầm vận hành
>  thoải mái cho quãng đường mỗi ngày và đủ chỗ cho số người Quý khách thường
>  chở."

Nhưng cũng KHÔNG mở vô hạn. Bốn tính năng cùng nói một lợi ích thì đọc như đọc
catalog, không như một lời tư vấn. `PlannedClaim.slot` chính là chiều lợi ích —
mỗi chiều nói MỘT lần.
"""

from __future__ import annotations

import pytest

from src.agents.domain.claim_policy import PlannedClaim
from src.agents.services.synthesis import (
    MAX_FALLBACK_CLAIMS,
    _deterministic_fallback_draft,
    select_fallback_claims,
)


def _claims(*pairs: tuple[str, str]) -> dict[str, PlannedClaim]:
    return {ph: PlannedClaim(ph, slot, f"noi ve {slot}") for ph, slot in pairs}


def test_khong_con_cat_cung_hai_claim() -> None:
    """Chín claim thì không được chỉ nói hai."""

    claims = _claims(
        ("CLAIM_VEHICLE_TYPE", "vehicle_type"),
        ("CLAIM_BUDGET_MAX_VND", "budget_max_vnd"),
        ("CLAIM_PASSENGER_COUNT", "passenger_count"),
        ("CLAIM_REQUIRED_RANGE_KM", "required_range_km"),
        ("CLAIM_HOME_CHARGING", "home_charging"),
        ("CLAIM_PURPOSE", "purpose"),
        ("CLAIM_ENERGY", "ENERGY_CONSUMPTION_KWH_PER_100KM"),
        ("CLAIM_MAX_LOAD", "max_load_kg"),
        ("CLAIM_HABIT", "habit_need_tags"),
    )

    chosen = select_fallback_claims(claims)

    assert len(chosen) > 2


def test_co_tran_tren_bon_claim() -> None:
    """Mở rộng KHÔNG có nghĩa là đổ hết ra."""

    claims = _claims(*[(f"CLAIM_{i}", f"slot_{i}") for i in range(9)])

    assert len(select_fallback_claims(claims)) <= MAX_FALLBACK_CLAIMS
    assert MAX_FALLBACK_CLAIMS == 4


def test_moi_chieu_loi_ich_chi_noi_mot_lan() -> None:
    """Bốn claim cùng `slot` là bốn cách nói một điều."""

    claims = _claims(
        ("CLAIM_A", "habit_need_tags"),
        ("CLAIM_B", "habit_need_tags"),
        ("CLAIM_C", "habit_need_tags"),
        ("CLAIM_D", "budget_max_vnd"),
    )

    chosen = select_fallback_claims(claims)

    slots = [claims[key].slot for key in chosen]
    assert len(slots) == len(set(slots)), f"trùng chiều: {slots}"
    assert "budget_max_vnd" in slots


def test_claim_noi_bat_van_dung_dau() -> None:
    """`CLAIM_STANDOUT` là điều đáng nói nhất — không được rơi khỏi danh sách."""

    claims = _claims(*[(f"CLAIM_{i}", f"slot_{i}") for i in range(8)])
    claims["CLAIM_STANDOUT"] = PlannedClaim("CLAIM_STANDOUT", "standout", "noi bat")

    chosen = select_fallback_claims(claims)

    assert chosen[0] == "CLAIM_STANDOUT"


def test_chi_mot_claim_thi_van_dung_duoc_cau() -> None:
    """Sàn 2 là mong muốn, không phải điều kiện — có một thì nói một."""

    chosen = select_fallback_claims(_claims(("CLAIM_ONLY", "budget_max_vnd")))

    assert chosen == ("CLAIM_ONLY",)


def test_khong_co_claim_nao_thi_khong_bia_ra_cau() -> None:
    assert select_fallback_claims({}) == ()


def test_ban_dung_tay_dung_dung_cac_claim_da_chon() -> None:
    """Không placeholder nào ngoài danh sách đã duyệt lọt vào câu."""

    claims = _claims(
        ("CLAIM_VEHICLE_TYPE", "vehicle_type"),
        ("CLAIM_BUDGET_MAX_VND", "budget_max_vnd"),
        ("CLAIM_PASSENGER_COUNT", "passenger_count"),
        ("CLAIM_REQUIRED_RANGE_KM", "required_range_km"),
        ("CLAIM_HOME_CHARGING", "home_charging"),
    )

    draft = _deterministic_fallback_draft(
        vehicle_name="VinFast VF 5 All New",
        fact_by_code={},
        claim_by_key=claims,
        quote_by_key={},
    )

    used = {part.split("}")[0] for part in draft.split("{")[1:]}
    assert used, "bản dựng tay phải dùng ít nhất một claim"
    assert used <= set(claims), f"placeholder lạ: {used - set(claims)}"
    assert 2 < len(used) <= MAX_FALLBACK_CLAIMS


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 9])
def test_cau_luon_doc_duoc_du_co_bao_nhieu_claim(count: int) -> None:
    claims = _claims(*[(f"CLAIM_{i}", f"slot_{i}") for i in range(count)])

    draft = _deterministic_fallback_draft(
        vehicle_name="VF 5",
        fact_by_code={},
        claim_by_key=claims,
        quote_by_key={},
    )

    assert draft.startswith("VF 5 ")
    assert draft.endswith(".")
    assert " và " in draft or count <= 2
