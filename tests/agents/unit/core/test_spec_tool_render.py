"""`spec_answer_by_group`: lối vào của tool `tra_thong_so` — cùng bộ render với đường từ khoá."""

from __future__ import annotations

from src.agents.core.render import SPEC_GROUP_KEYS, spec_answer, spec_answer_by_group
from src.agents.domain.spec_tool import SPEC_GROUPS

SPECS = {"cargo_volume_standard_l": 423, "range_km": 460}


def test_khoa_nhom_khop_domain_va_render() -> None:
    """Hai bản khoá nhóm (schema tool và bảng render) không được trôi nhau."""
    assert tuple(SPEC_GROUPS.keys()) == SPEC_GROUP_KEYS


def test_nhom_hop_le_ra_cung_giong_voi_duong_tu_khoa() -> None:
    by_group = spec_answer_by_group(vehicle_name="VF 6", group="cop", specs=SPECS)
    by_keyword = spec_answer(vehicle_name="VF 6", question="cốp xe rộng không", specs=SPECS)
    assert by_group == by_keyword
    assert by_group is not None and "423" in by_group


def test_nhom_la_tra_none() -> None:
    assert spec_answer_by_group(vehicle_name="VF 6", group="mau_son", specs=SPECS) is None


def test_nhom_khong_co_du_lieu_tra_none() -> None:
    assert spec_answer_by_group(vehicle_name="VF 6", group="yen", specs=SPECS) is None


def test_hoi_tam_di_khong_bi_nham_sang_sac() -> None:
    """ACC-07: 'đi được bao xa mỗi lần sạc' hỏi TẦM ĐI, không phải thời gian sạc."""
    specs = {"range_km": 460, "fast_charge_time_minutes": 30, "charging_time_minutes": 300}
    ans = spec_answer(vehicle_name="VF 5", question="VF 5 đi được bao xa mỗi lần sạc", specs=specs)
    assert ans is not None
    assert "460" in ans and "km" in ans
    assert "phút" not in ans  # KHONG tra thoi gian sac


def test_hoi_sac_van_ra_thoi_gian_sac() -> None:
    """Câu chỉ hỏi sạc (không kèm 'bao xa') vẫn ra thời gian sạc như cũ."""
    specs = {"range_km": 460, "fast_charge_time_minutes": 30}
    ans = spec_answer(vehicle_name="VF 5", question="VF 5 sạc nhanh bao lâu", specs=specs)
    assert ans is not None and "phút" in ans


def test_hoi_tam_hoat_dong_ra_range() -> None:
    specs = {"range_km": 460}
    ans = spec_answer(vehicle_name="VF 5", question="tầm hoạt động của VF 5 bao nhiêu", specs=specs)
    assert ans is not None and "460" in ans
