"""Phase 0 Customer 360: quy ước danh tính và quyền xem khách của TVV khác."""

from __future__ import annotations

from src.agents.domain.staff_access import can_list_other_advisor, is_admin, staff_identifiers


def test_dinh_danh_gom_ca_id_va_email() -> None:
    assert staff_identifiers("adv-1", "a@x.vn") == ("adv-1", "a@x.vn")
    assert staff_identifiers("adv-1", None) == ("adv-1",)
    assert staff_identifiers("a@x.vn", "a@x.vn") == ("a@x.vn",)


def test_chi_admin_xem_duoc_khach_cua_tvv_khac() -> None:
    mine = staff_identifiers("adv-1", "a@x.vn")
    assert can_list_other_advisor("advisor", mine, None)
    assert can_list_other_advisor("advisor", mine, "adv-1")
    assert can_list_other_advisor("advisor", mine, "a@x.vn")
    assert not can_list_other_advisor("advisor", mine, "adv-2")
    assert can_list_other_advisor("admin", mine, "adv-2")


def test_is_admin_khong_phan_biet_hoa_thuong() -> None:
    assert is_admin("admin") and is_admin("ADMIN")
    assert not is_admin("advisor")
