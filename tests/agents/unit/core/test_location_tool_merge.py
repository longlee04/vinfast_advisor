"""`_merge_location_tool_args`: LLM chỉ lấp chỗ trống, loại lạ bị vứt."""

from __future__ import annotations

from src.agents.core.act import _location_tool_record, _merge_location_tool_args
from src.agents.domain.location_tool import LocationToolArgs
from src.agents.domain.nearby_location import LocationKind


def test_none_giu_nguyen() -> None:
    kinds = (LocationKind.SHOWROOM_CAR,)
    assert _merge_location_tool_args(kinds, "Hà Nội", None) == (kinds, "Hà Nội")


def test_bo_do_tu_khoa_da_ra_thi_thang_tool() -> None:
    kinds = (LocationKind.SHOWROOM_CAR,)
    merged, area = _merge_location_tool_args(kinds, None, LocationToolArgs(kinds=("BATTERY_SWAP_CABINET",), area="Huế"))
    assert merged == kinds
    assert area == "Huế"


def test_lap_loai_khi_do_khong_ra() -> None:
    merged, area = _merge_location_tool_args((), None, LocationToolArgs(kinds=("CHARGING_STATION_CAR",), area=None))
    assert merged == (LocationKind.CHARGING_STATION_CAR,)
    assert area is None


def test_loai_la_bi_vut() -> None:
    merged, _ = _merge_location_tool_args((), None, LocationToolArgs(kinds=("TRAM_XANG", "SHOWROOM_CAR"), area=None))
    assert merged == (LocationKind.SHOWROOM_CAR,)


def test_khu_vuc_rong_bi_bo() -> None:
    _, area = _merge_location_tool_args((), "Đà Nẵng", LocationToolArgs(kinds=(), area="   "))
    assert area == "Đà Nẵng"


def test_record_vet_du_ba_tang() -> None:
    record = _location_tool_record(
        known_kinds=(),
        known_area=None,
        tool_args=LocationToolArgs(kinds=("CHARGING_STATION_CAR",), area="Thủ Đức"),
        kinds_after=(LocationKind.CHARGING_STATION_CAR,),
        area_after="Thủ Đức",
    )
    assert record["tool"] == "tim_diem_dich_vu"
    assert record["known"] == {"kinds": [], "area": None}
    assert record["returned"] == {"kinds": ["CHARGING_STATION_CAR"], "area": "Thủ Đức"}
    assert record["used"] == {"kinds": ["CHARGING_STATION_CAR"], "area": "Thủ Đức"}
