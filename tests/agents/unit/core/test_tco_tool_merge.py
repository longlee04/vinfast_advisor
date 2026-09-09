"""`_merge_tco_tool_args`: tham số LLM chọn chỉ được LẤP CHỖ TRỐNG, không đè slot."""

from __future__ import annotations

from src.agents.core.act import _merge_tco_tool_args
from src.agents.domain.tco_tool import TcoToolArgs


def test_none_giu_nguyen() -> None:
    assert _merge_tco_tool_args(40, "HN", None) == (40, "HN")


def test_slot_da_co_thi_thang_tool() -> None:
    daily, code = _merge_tco_tool_args(40, "HN", TcoToolArgs(daily_km=60, province="Đà Nẵng"))
    assert (daily, code) == (40, "HN")


def test_lap_km_khi_slot_thieu() -> None:
    daily, code = _merge_tco_tool_args(None, None, TcoToolArgs(daily_km=60, province=None))
    assert (daily, code) == (60, None)


def test_km_ngoai_khoang_bi_bo() -> None:
    assert _merge_tco_tool_args(None, None, TcoToolArgs(daily_km=5000, province=None)) == (None, None)
    assert _merge_tco_tool_args(None, None, TcoToolArgs(daily_km=0, province=None)) == (None, None)


def test_tinh_ra_ma_khi_slot_thieu() -> None:
    daily, code = _merge_tco_tool_args(None, None, TcoToolArgs(daily_km=None, province="hà nội"))
    assert daily is None
    assert code == "HN"


def test_tinh_khong_tra_ra_ma_thi_bo() -> None:
    assert _merge_tco_tool_args(None, None, TcoToolArgs(daily_km=None, province="Paris")) == (None, None)


def test_record_vet_du_ba_tang() -> None:
    from src.agents.core.act import _tco_tool_record

    record = _tco_tool_record(
        known_daily_km=None,
        known_province=None,
        tool_args=TcoToolArgs(daily_km=60, province="Đà Nẵng"),
        daily_after=60,
        province_after="DDN",
    )
    assert record["tool"] == "tinh_chi_phi"
    assert record["known"] == {"daily_km": None, "province": None}
    assert record["returned"] == {"daily_km": 60, "province": "Đà Nẵng"}
    assert record["used"] == {"daily_km": 60, "province_code": "DDN"}


def test_record_vet_khi_resolver_hong() -> None:
    from src.agents.core.act import _tco_tool_record

    record = _tco_tool_record(
        known_daily_km=40, known_province="HN", tool_args=None, daily_after=40, province_after="HN"
    )
    assert record["returned"] is None
    assert record["used"] == {"daily_km": 40, "province_code": "HN"}
