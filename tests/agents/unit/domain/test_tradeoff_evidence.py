"""Câu trade-off là một CLAIM SO SÁNH — phải có số của cả hai xe.

Kế hoạch 2026-08-28 nêu ví dụ:

> "VF 5 có thể không thoải mái bằng VF 6"

Đó là khẳng định về một chiếc xe KHÁC. Sinh nó từ template trống, hay từ nhãn
phân khúc chung chung, là đúng loại claim mà validator sinh ra để chặn — chỉ khác
là lần này ta tự bịa thay vì để LLM bịa.

Luật: có số đã xác minh của **cả hai xe** trên **cùng một chiều** thì mới được
nói; thiếu thì **bỏ hẳn** câu trade-off, không viết câu chung chung cho đủ cấu
trúc.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agents.domain.tradeoff import ComparisonFact, plan_tradeoff


def _fact(code: str, vehicle: str, value: str) -> ComparisonFact:
    return ComparisonFact(fact_code=code, vehicle_name=vehicle, value=Decimal(value))


def test_du_so_ca_hai_xe_thi_noi_duoc() -> None:
    plan = plan_tradeoff(
        subject="VinFast VF 5 All New",
        subject_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 5 All New", "1100"),
        alternative_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 6 Plus", "1400"),
    )

    assert plan is not None
    assert plan.alternative_name == "VinFast VF 6 Plus"
    assert plan.difference == Decimal("300")


def test_thieu_so_cua_xe_doi_chieu_thi_bo_han() -> None:
    """Không có số của xe kia thì không biết nó 'lớn hơn' ở đâu."""

    assert (
        plan_tradeoff(
            subject="VinFast VF 5 All New",
            subject_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 5 All New", "1100"),
            alternative_fact=None,
        )
        is None
    )


def test_thieu_so_cua_chinh_no_thi_cung_bo_han() -> None:
    assert (
        plan_tradeoff(
            subject="VinFast VF 5 All New",
            subject_fact=None,
            alternative_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 6 Plus", "1400"),
        )
        is None
    )


def test_hai_chieu_khac_nhau_thi_khong_so_duoc() -> None:
    """So khoang hành lý với tầm chạy là so hai thứ không cùng đơn vị."""

    assert (
        plan_tradeoff(
            subject="VinFast VF 5 All New",
            subject_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 5 All New", "1100"),
            alternative_fact=_fact("RANGE_KM", "VinFast VF 6 Plus", "480"),
        )
        is None
    )


@pytest.mark.parametrize(("subject_value", "alt_value"), [("1400", "1100"), ("1100", "1100")])
def test_xe_doi_chieu_khong_hon_thi_khong_co_trade_off(subject_value: str, alt_value: str) -> None:
    """Trade-off chỉ có nghĩa khi xe kia THẬT SỰ hơn ở chiều đó.

    Bằng nhau hoặc kém hơn mà vẫn mời khách xem sang là đẩy họ đi vô cớ.
    """

    assert (
        plan_tradeoff(
            subject="VinFast VF 5 All New",
            subject_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 5 All New", subject_value),
            alternative_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 6 Plus", alt_value),
        )
        is None
    )


def test_so_sanh_chinh_no_voi_chinh_no_thi_vo_nghia() -> None:
    assert (
        plan_tradeoff(
            subject="VinFast VF 5 All New",
            subject_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 5 All New", "1100"),
            alternative_fact=_fact("CARGO_VOLUME_MAXIMUM_L", "VinFast VF 5 All New", "1400"),
        )
        is None
    )
