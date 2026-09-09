"""Chuẩn hoá tất định của lõi v2 (spec mục 5): tên xe, tiền, choice_ref.

Dùng `entity_catalog` và `budget_parsing` THẬT — không fake, không DB. Hai module
đó là nguồn sự thật; test ở đây chốt phần lõi v2 GỌI chúng cho đúng.
"""

from __future__ import annotations

import pytest

from src.agents.core.validate import (
    VehicleDirectory,
    VehicleRef,
    budget_slots,
    resolve_choice_ref,
    resolve_vehicle_ids,
    validate_slots,
    vehicle_type_slot,
)
from src.agents.domain.values import SlotName as N

DIR = VehicleDirectory(
    refs=(
        VehicleRef(vehicle_id="v1", display_name="VF 5 Plus"),
        VehicleRef(vehicle_id="v2", display_name="VF 8 Eco"),
        VehicleRef(vehicle_id="v3", display_name="Evo 200"),
    )
)
IDS = ("v1", "v2", "v3")


# ---------- tên xe ----------


@pytest.mark.parametrize(
    ("mention", "expect"),
    [
        ("VF 5 Plus", "v1"),
        ("vf 5 plus", "v1"),
        ("vf5plus", "v1"),
        ("vf nam plus", "v1"),
        ("VF 8 Eco", "v2"),
        ("Evo 200", "v3"),
        ("evo200", "v3"),
        ("evo hai tram", "v3"),
    ],
)
def test_resolve_ten_xe(mention: str, expect: str) -> None:
    assert DIR.resolve(mention) == expect


@pytest.mark.parametrize("mention", ["VF 9", "Honda SH", "", "   ", "xe điện"])
def test_ten_khong_khop_thi_bo_khong_doan(mention: str) -> None:
    assert DIR.resolve(mention) is None


def test_resolve_vehicle_ids_giu_thu_tu_khu_trung_bo_la() -> None:
    assert resolve_vehicle_ids(["VF 8 Eco", "vf5plus", "VF 8 Eco", "Kia Morning"], DIR) == ("v2", "v1")


def test_resolve_vehicle_ids_rong() -> None:
    assert resolve_vehicle_ids([], DIR) == ()
    assert resolve_vehicle_ids(["VF 5 Plus"], VehicleDirectory()) == ()


def test_name_of_va_prompt_lines() -> None:
    assert DIR.name_of("v2") == "VF 8 Eco"
    assert DIR.name_of(None) is None
    assert DIR.name_of("khong-co") is None
    lines = DIR.prompt_lines()
    assert len(lines) == 3
    assert lines[0].startswith("VF 5 Plus — ")
    assert "vf5plus" in lines[0]
    # Thứ tự alias phải ỔN ĐỊNH: `build_vehicle_aliases` dựng qua `set`, không
    # sắp thì prompt đổi mỗi lần chạy và không bao giờ cache được.
    assert DIR.prompt_lines() == lines


# ---------- tiền ----------


def test_budget_uoc_luong_co_du_ba_moc() -> None:
    assert budget_slots("tầm 700 triệu") == {
        N.BUDGET_MAX_VND: 700_000_000,
        N.BUDGET_MIN_VND: 600_000_000,
        N.BUDGET_STATED_VND: 700_000_000,
    }


def test_budget_khoang_khong_co_stated() -> None:
    assert budget_slots("từ 300 đến 500 triệu") == {
        N.BUDGET_MAX_VND: 500_000_000,
        N.BUDGET_MIN_VND: 300_000_000,
    }


def test_budget_chi_tran() -> None:
    assert budget_slots("dưới 800 triệu") == {N.BUDGET_MAX_VND: 800_000_000}


@pytest.mark.parametrize("text", [None, "", "xanh lá cây", "em chưa biết"])
def test_budget_khong_hieu_thi_bo_slot(text: str | None) -> None:
    assert budget_slots(text) == {}


def test_budget_luon_la_int_khong_bao_gio_decimal() -> None:
    values = budget_slots("khoảng 1 tỷ").values()
    assert values
    for value in values:
        assert type(value) is int


# ---------- loại xe ----------


@pytest.mark.parametrize(
    ("raw", "expect"), [("CAR", "CAR"), ("car", "CAR"), ("electric_motorbike", "ELECTRIC_MOTORBIKE")]
)
def test_vehicle_type_hop_le(raw: str, expect: str) -> None:
    assert vehicle_type_slot(raw) == expect


@pytest.mark.parametrize("raw", [None, "", "ô tô", "SUV", "XE_MAY", "CAR2"])
def test_vehicle_type_la_thi_bo(raw: str | None) -> None:
    assert vehicle_type_slot(raw) is None


# ---------- gộp slot ----------


def test_validate_slots_day_du() -> None:
    slots = validate_slots(
        vehicle_type="CAR",
        budget_text="dưới 800 triệu",
        purpose="  đi làm  ",
        seats=5,
        daily_km=30,
        features=["cảm biến lùi", "", "cảm biến lùi", "cửa sổ trời"],
        region="Hà Nội",
    )
    assert slots == {
        N.VEHICLE_TYPE: "CAR",
        N.BUDGET_MAX_VND: 800_000_000,
        N.PURPOSE: "đi làm",
        N.PASSENGER_COUNT: 5,
        N.REQUIRED_RANGE_KM: 30,
        N.HABIT_NEED_TAGS: ["cảm biến lùi", "cửa sổ trời"],
        N.REGISTRATION_PROVINCE: "Hà Nội",
    }
    assert all(isinstance(key, N) for key in slots)


def test_validate_slots_rong_khi_khong_co_gi() -> None:
    assert validate_slots() == {}


@pytest.mark.parametrize(("seats", "km"), [(0, 0), (-1, -5), (None, None)])
def test_so_khong_duong_thi_bo(seats: int | None, km: int | None) -> None:
    slots = validate_slots(seats=seats, daily_km=km)
    assert N.PASSENGER_COUNT not in slots and N.REQUIRED_RANGE_KM not in slots


def test_features_rong_thi_khong_ghi_slot() -> None:
    assert validate_slots(features=["", "  "]) == {}


# ---------- choice_ref ----------


@pytest.mark.parametrize(
    ("raw", "expect"),
    [
        ("1", "v1"),
        ("2", "v2"),
        ("3", "v3"),
        ("mẫu đầu tiên", "v1"),
        ("đầu tiên", "v1"),
        ("thứ hai", "v2"),
        ("cái cuối", "v3"),
        ("cuối cùng", "v3"),
        ("v2", "v2"),
    ],
)
def test_choice_ref_tro_duoc(raw: str, expect: str) -> None:
    assert resolve_choice_ref(raw, recommended_ids=IDS) == expect


def test_choice_ref_theo_ten_xe() -> None:
    assert resolve_choice_ref("VF 8 Eco", recommended_ids=IDS, directory=DIR) == "v2"


def test_choice_ref_uu_tien_vehicle_ids_da_giai() -> None:
    assert resolve_choice_ref("cái này", recommended_ids=IDS, vehicle_ids=("v3",)) == "v3"


@pytest.mark.parametrize("raw", [None, "", "mẫu thứ chín", "9", "0", "Honda SH", "cái nào cũng được"])
def test_choice_ref_khong_tro_duoc_thi_none(raw: str | None) -> None:
    assert resolve_choice_ref(raw, recommended_ids=IDS, directory=DIR) is None


def test_choice_ref_khong_co_de_xuat_thi_none() -> None:
    assert resolve_choice_ref("1", recommended_ids=()) is None


def test_nut_khung_gio_giu_nguyen_van() -> None:
    nut = "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA"
    assert resolve_choice_ref(nut, recommended_ids=()) == nut
    assert resolve_choice_ref(nut, recommended_ids=IDS) == nut


# ---------- fix round 2: choice_ref không được bịa, số thứ tự rộng hơn, trần slot ----------


def test_choice_ref_rong_khong_bia_ra_xe_tu_vehicle_ids() -> None:
    """Finding 3: `raw` trống thì KHÔNG bao giờ có lựa chọn, dù `vehicle_ids` trỏ vào đề xuất."""

    assert resolve_choice_ref("", recommended_ids=("id1", "id2"), vehicle_ids=("id1",)) is None
    assert resolve_choice_ref(None, recommended_ids=("id1", "id2"), vehicle_ids=("id1",)) is None


def test_choice_ref_khong_co_de_xuat_thi_vehicle_ids_cung_khong_cuu() -> None:
    assert resolve_choice_ref("VF 8 Eco", recommended_ids=(), vehicle_ids=("v2",)) is None


IDS4 = ("v1", "v2", "v3", "v4")


@pytest.mark.parametrize(
    ("raw", "expect"),
    [
        ("cái thứ 2", "v2"),
        ("mẫu thứ hai", "v2"),
        ("thứ tư", "v4"),
        ("thu 2", "v2"),
        ("chiếc thứ 3", "v3"),
        ("xe số 1", "v1"),
        ("cái thứ nhất", "v1"),
    ],
)
def test_choice_ref_so_thu_tu_viet_kieu_gi_cung_tro_duoc(raw: str, expect: str) -> None:
    assert resolve_choice_ref(raw, recommended_ids=IDS4) == expect


def test_button_prefix_la_ma_nut_that_khong_phai_hai_gach() -> None:
    """Finding 9: nhận ra nút ≠ tách nút — tiền tố phải là mã nút thật, không phải mọi chuỗi bắt đầu bằng `__`."""

    from src.agents.core.validate import BUTTON_PREFIX

    assert BUTTON_PREFIX == "__lichlaithu__"
    assert resolve_choice_ref("__khac__|abc", recommended_ids=IDS) is None


@pytest.mark.parametrize(("seats", "expect"), [(1, 1), (5, 5), (9, 9), (10, None), (0, None), (-3, None), (99, None)])
def test_seats_ngoai_khoang_thi_bo(seats: int, expect: int | None) -> None:
    slots = validate_slots(seats=seats)
    assert slots.get(N.PASSENGER_COUNT) == expect


@pytest.mark.parametrize(("km", "expect"), [(1, 1), (40, 40), (1000, 1000), (1001, None), (0, None), (100000, None)])
def test_daily_km_ngoai_khoang_thi_bo(km: int, expect: int | None) -> None:
    slots = validate_slots(daily_km=km)
    assert slots.get(N.REQUIRED_RANGE_KM) == expect


# ---------- tên xe THẬT của catalog: tiền tố hãng, dòng xe, quét trong câu ----------
#
# Bằng chứng prod: `_vehicle_directory` dựng 46 ref với tên kiểu "VinFast VF 8
# All New", nhưng `resolve` trượt HẾT mọi cách khách gõ ("VF 8", "vf8",
# "vin fast vf9", "Klara Neo"). Bộ ref dưới đây chép đúng hình dạng tên đó.

PROD = VehicleDirectory(
    refs=(
        VehicleRef(vehicle_id="c8new", display_name="VinFast VF 8 All New"),
        VehicleRef(vehicle_id="c8eco", display_name="VinFast VF 8 Eco Extended Range"),
        VehicleRef(vehicle_id="c8plus", display_name="VinFast VF 8 Plus Extended Range"),
        VehicleRef(vehicle_id="c9", display_name="VinFast VF 9 Plus"),
        VehicleRef(vehicle_id="c3", display_name="VinFast VF 3"),
        VehicleRef(vehicle_id="mklaraneo", display_name="VinFast Klara Neo"),
        VehicleRef(vehicle_id="mklaras", display_name="VinFast Klara S"),
        VehicleRef(vehicle_id="mamio", display_name="VinFast Amio S"),
        VehicleRef(vehicle_id="mfeliz", display_name="VinFast Feliz S"),
        VehicleRef(vehicle_id="mevo200", display_name="VinFast Evo 200"),
        VehicleRef(vehicle_id="mevogrand", display_name="VinFast Evo Grand"),
    )
)


@pytest.mark.parametrize(
    ("mention", "expect"),
    [
        # nguyên văn như catalog
        ("VinFast VF 8 All New", "c8new"),
        ("vinfast vf 8 all new", "c8new"),
        ("vinfastvf8allnew", "c8new"),
        # BỎ tiền tố hãng — cách khách gõ thường gặp nhất
        ("VF 8 All New", "c8new"),
        ("vf 8 all new", "c8new"),
        ("vf8allnew", "c8new"),
        ("Klara Neo", "mklaraneo"),
        ("klaraneo", "mklaraneo"),
        ("Amio S", "mamio"),
        ("Evo 200", "mevo200"),
        ("evo200", "mevo200"),
        # tên DÒNG xe (nhiều bản) → bản "All New" nếu có
        ("VF 8", "c8new"),
        ("vf 8", "c8new"),
        ("vf8", "c8new"),
        ("vf tam", "c8new"),
        ("vinfast vf8", "c8new"),
        ("vin fast vf 8", "c8new"),
        # dòng chỉ có một bản
        ("VF 9", "c9"),
        ("vf9", "c9"),
        ("vin fast vf9", "c9"),
        ("VF 3", "c3"),
        ("vf3", "c3"),
        ("amio", "mamio"),
        ("evo", "mevo200"),
    ],
)
def test_resolve_ten_that_cua_catalog(mention: str, expect: str) -> None:
    assert PROD.resolve(mention) == expect


@pytest.mark.parametrize("mention", ["tesla model y", "Tesla Model Y", "model y", "vf", "vin fast", "VinFast", "xe"])
def test_ten_ngoai_danh_muc_van_khong_doan(mention: str) -> None:
    """ "vf"/"vinfast" trần KHÔNG được trỏ vào một xe nào: đó là tên hãng, không phải mẫu."""

    assert PROD.resolve(mention) is None


def test_dong_xe_khong_co_all_new_thi_lay_ban_ten_ngan_nhat() -> None:
    """ "Klara" có hai bản, không bản nào tên "Klara All New" → bản tên ngắn nhất."""

    assert PROD.resolve("Klara") == "mklaras"
    assert PROD.resolve("klara") == "mklaras"


@pytest.mark.parametrize(
    ("mention", "expect"),
    [
        ("VF 8", ("c8new", "c8eco", "c8plus")),
        ("vf8", ("c8new", "c8eco", "c8plus")),
        ("VinFast VF 8", ("c8new", "c8eco", "c8plus")),
        # một BẢN cụ thể vẫn trả về cả dòng — chỗ gọi so sánh/duyệt cần cả bộ
        ("VF 8 Eco Extended Range", ("c8new", "c8eco", "c8plus")),
        ("Klara", ("mklaraneo", "mklaras")),
        ("evo", ("mevo200", "mevogrand")),
        ("VF 3", ("c3",)),
        ("tesla model y", ()),
        ("", ()),
    ],
)
def test_family_tra_ve_moi_ban_cua_dong(mention: str, expect: tuple[str, ...]) -> None:
    assert PROD.family(mention) == expect


@pytest.mark.parametrize(
    ("message", "expect"),
    [
        ("anh đang quan tâm vf8", ("c8new",)),
        ("so sánh VF 8 với Tesla Model Y", ("c8new",)),
        ("VF 3 giá bao nhiêu", ("c3",)),
        ("tôi cần vin fast vf9", ("c9",)),
        ("cho em xem Klara Neo với Evo 200", ("mklaraneo", "mevo200")),
        ("em muốn tư vấn xe", ()),
        ("chào em", ()),
        ("", ()),
    ],
)
def test_scan_bat_ten_xe_trong_cau_khach(message: str, expect: tuple[str, ...]) -> None:
    assert PROD.scan(message) == expect


def test_scan_uu_tien_ten_dai_nhat_khong_cat_vun() -> None:
    assert PROD.scan("cho em hỏi VF 8 Plus Extended Range") == ("c8plus",)
