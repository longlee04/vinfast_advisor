"""Đối chiếu xe với nhu cầu khách — thuần, tất định (`core/fit.py`)."""

from __future__ import annotations

from src.agents.core.actions import FIT_PARTIAL, FIT_UNFIT, FIT_YES
from src.agents.core.fit import (
    LONG_TRIP_RANGE_KM,
    MISS_PRICE,
    MISS_RANGE,
    MISS_SEATS,
    MISS_TRUNK,
    CustomerNeed,
    VehicleSpec,
    assess,
    build_spec,
    compare_fit,
    customer_need,
    tied,
)
from src.agents.domain.values import SlotName as N

VF2 = VehicleSpec(vehicle_id="v2", name="VF 2", seats=4, range_km=210, trunk_litres=200, price_vnd=260_000_000)
VF5 = VehicleSpec(vehicle_id="v5", name="VF 5", seats=5, range_km=326, trunk_litres=300, price_vnd=480_000_000)


def test_du_moi_tieu_chi_thi_hop() -> None:
    need = CustomerNeed(budget_max_vnd=500_000_000, passenger_count=4)
    result = assess(VF2, need)
    assert result.verdict == FIT_YES
    assert 1 <= len(result.reasons) <= 3
    assert result.alternative_id == ""


def test_thieu_tam_chay_cho_chuyen_di_xa_la_hop_mot_phan() -> None:
    need = CustomerNeed(budget_max_vnd=500_000_000, passenger_count=4, long_trip=True)
    result = assess(VF2, need)
    assert result.verdict == FIT_PARTIAL
    assert MISS_RANGE in result.missed
    # Lý do TRƯỢT phải đứng trước: đó là thứ khách cần nghe.
    assert str(VF2.range_km) in result.reasons[0]


def test_truot_het_thi_chua_hop() -> None:
    need = CustomerNeed(budget_max_vnd=200_000_000, passenger_count=7, long_trip=True)
    result = assess(VF2, need)
    assert result.verdict == FIT_UNFIT
    assert set(result.missed) == {MISS_SEATS, MISS_RANGE, MISS_TRUNK, MISS_PRICE}


def test_khong_co_gi_de_doi_chieu_thi_noi_that_khong_ket_luan_hop() -> None:
    result = assess(VehicleSpec(vehicle_id="v9", name="VF 9"), CustomerNeed())
    assert result.verdict == FIT_PARTIAL
    assert result.reasons and result.missed == ()


def test_mau_thay_the_phai_va_dung_cho_dang_thieu() -> None:
    need = CustomerNeed(budget_max_vnd=500_000_000, passenger_count=4, long_trip=True)
    result = assess(VF2, need, alternatives=(VF5,))
    assert result.alternative_id == "v5"
    assert result.alternative_name == "VF 5"


def test_mau_thay_the_khong_va_duoc_cho_thieu_thi_khong_de_xuat() -> None:
    need = CustomerNeed(passenger_count=4, long_trip=True)
    kem = VehicleSpec(vehicle_id="v3", name="VF 3", seats=4, range_km=210)
    assert assess(VF2, need, alternatives=(kem,)).alternative_id == ""


def test_xe_da_hop_thi_khong_bao_gio_moi_doi_mau() -> None:
    need = CustomerNeed(passenger_count=4)
    assert assess(VF2, need, alternatives=(VF5,)).alternative_id == ""


def test_nguong_di_xa_doc_tu_hang_so_chu_khong_bia_trong_test() -> None:
    need = CustomerNeed(long_trip=True)
    du = VehicleSpec(vehicle_id="v7", name="VF 7", range_km=LONG_TRIP_RANGE_KM)
    assert assess(du, need).verdict == FIT_YES


def test_nhu_cau_doc_tu_slot_ke_ca_muc_dich_viet_tu_do() -> None:
    need = customer_need(
        {
            N.BUDGET_MAX_VND: 500_000_000,
            N.PASSENGER_COUNT: 4,
            N.PURPOSE: "đi chơi xa cùng gia đình",
        }
    )
    assert need.budget_max_vnd == 500_000_000
    assert need.passenger_count == 4
    assert need.long_trip is True
    assert need.family is True


def test_nhu_cau_doc_them_tu_the_nhu_cau() -> None:
    need = customer_need({N.HABIT_NEED_TAGS: ["LONG_RANGE"]})
    assert need.long_trip is True


def test_muc_dich_noi_thanh_khong_thanh_chuyen_di_xa() -> None:
    assert customer_need({N.PURPOSE: "đi làm nội thành"}).long_trip is False


def test_build_spec_doc_dung_khoa_catalog_cho_ca_hai_loai_xe() -> None:
    car = build_spec(
        vehicle_id="v5",
        name="VF 5",
        specs={"seat_count": "5", "range_km": "326.00", "cargo_volume_standard_l": "300"},
        price_vnd="480000000",
    )
    assert (car.seats, car.range_km, car.trunk_litres, car.price_vnd) == (5, 326, 300, 480_000_000)
    bike = build_spec(vehicle_id="m1", name="Evo", specs={"range_max_km": 203}, price_vnd=None)
    assert bike.range_km == 203 and bike.price_vnd is None


def test_build_spec_bo_qua_gia_tri_rac_thay_vi_no() -> None:
    spec = build_spec(vehicle_id="v1", name="X", specs={"seat_count": "khong ro", "range_km": None}, price_vnd="")
    assert (spec.seats, spec.range_km, spec.price_vnd) == (None, None, None)


def test_compare_fit_xep_mau_hop_nhat_len_dau() -> None:
    need = CustomerNeed(budget_max_vnd=600_000_000, passenger_count=4, long_trip=True)
    order = compare_fit((VF2, VF5), need)
    assert [spec.vehicle_id for spec, _ in order] == ["v5", "v2"]
    assert order[0][1].checked > 0


def test_compare_fit_khong_co_nhu_cau_nao_thi_khong_ket_luan() -> None:
    order = compare_fit((VF2, VF5), CustomerNeed())
    assert all(assessment.checked == 0 for _, assessment in order)


# ---------- prod vòng 10: "đi chơi xa" phải kéo TẦM CHẠY vào kết luận ----------


VF8 = VehicleSpec(vehicle_id="v8", name="VF 8", seats=5, range_km=470, trunk_litres=376, price_vnd=1_020_000_000)


def test_nhu_cau_doc_duoc_tu_chinh_cau_khach_vua_go() -> None:
    """Lượt prod vòng 10: đã chọn VF 2, khách gõ "gia đình tôi có 4 người, tôi
    muốn sử dụng đi chơi xa" và lõi kết luận "hợp: 4 chỗ, giá trong ngân sách" —
    tầm chạy 210 km không được nhắc tới. Slot `purpose` lượt đó không chở chữ
    "đi chơi xa" (LLM rút ra số người là chính), nên nhu cầu phải đọc được từ
    CHÍNH câu khách vừa gõ, không chỉ từ slot đã chốt."""

    need = customer_need({N.PASSENGER_COUNT: 4}, user_message="gia đình tôi có 4 người, tôi muốn sử dụng đi chơi xa")
    assert need.long_trip is True
    assert need.family is True


def test_vf2_di_choi_xa_thi_chi_hop_mot_phan_va_co_mau_thay_the() -> None:
    need = customer_need(
        {N.BUDGET_MAX_VND: 500_000_000, N.PASSENGER_COUNT: 4},
        user_message="gia đình tôi có 4 người, tôi muốn sử dụng đi chơi xa",
    )
    result = assess(VF2, need, alternatives=(VF5,))
    assert result.verdict == FIT_PARTIAL
    assert MISS_RANGE in result.missed
    assert "210" in result.reasons[0] and "sạc dọc đường" in result.reasons[0]
    assert result.alternative_name == "VF 5"


def test_vf8_di_xa_thi_hop() -> None:
    need = customer_need({N.PASSENGER_COUNT: 4}, user_message="tôi hay đi xa, đi tỉnh cuối tuần")
    assert assess(VF8, need).verdict == FIT_YES


def test_mau_thay_the_lay_tam_chay_cao_nhat_con_trong_ngan_sach_noi_rong() -> None:
    """Ngân sách 900 triệu: VF 8 (1,02 tỷ) còn trong mức nới 20% nên nó — chiếc
    đi xa được nhất — mới là mẫu vá đúng chỗ thiếu."""

    need = CustomerNeed(budget_max_vnd=900_000_000, passenger_count=4, long_trip=True)
    assert assess(VF2, need, alternatives=(VF5, VF8)).alternative_id == "v8"


def test_mau_thay_the_vuot_qua_muc_noi_rong_thi_khong_moi() -> None:
    """Ngân sách 500 triệu: VF 8 vượt xa mức nới 20% (600 triệu) — mời khách một
    chiếc gấp đôi tiền là không trả lời câu hỏi của họ."""

    need = CustomerNeed(budget_max_vnd=500_000_000, passenger_count=4, long_trip=True)
    assert assess(VF2, need, alternatives=(VF8, VF5)).alternative_id == "v5"


def test_cho_nhieu_do_cung_keo_cop_vao_doi_chieu() -> None:
    need = customer_need({}, user_message="tôi hay chở nhiều đồ")
    result = assess(VF2, need)
    assert MISS_TRUNK in result.missed


def test_di_xa_thi_tam_chay_pha_the_ngang_nhau_khi_so_sanh() -> None:
    """Hai mẫu cùng số tiêu chí ĐẠT/TRƯỢT: khách đi xa thì chiếc chạy được xa
    hơn mới là chiếc hợp hơn, không phải "bám sát ngang nhau"."""

    xa = VehicleSpec(vehicle_id="a", name="A", seats=5, range_km=450, price_vnd=600_000_000)
    gan = VehicleSpec(vehicle_id="b", name="B", seats=5, range_km=320, price_vnd=600_000_000)
    need = CustomerNeed(budget_max_vnd=700_000_000, passenger_count=4, long_trip=True)
    order = compare_fit((gan, xa), need)
    assert [spec.vehicle_id for spec, _ in order] == ["a", "b"]
    assert tied(gan, xa, need) is False
    assert tied(xa, VehicleSpec(vehicle_id="c", name="C", seats=5, range_km=450, price_vnd=600_000_000), need) is True


def test_khong_di_xa_thi_tam_chay_khong_pha_the_ngang_nhau() -> None:
    xa = VehicleSpec(vehicle_id="a", name="A", seats=5, range_km=450, price_vnd=600_000_000)
    gan = VehicleSpec(vehicle_id="b", name="B", seats=5, range_km=320, price_vnd=600_000_000)
    need = CustomerNeed(budget_max_vnd=700_000_000, passenger_count=4)
    assert tied(gan, xa, need) is True
