"""[COMPARE_VEHICLES] Test tối thiểu cho tool ghép bảng so sánh.

Không có DB ở đây là CHỦ ĐÍCH, không phải để chạy nhanh: tool được thiết kế
thuần để luật "thiếu xe thì báo thiếu" kiểm được mà không cần Postgres.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.agents.contracts import VehicleFacts
from src.agents.domain.values import VehicleType
from src.agents.tools.compare_vehicles import compare_vehicles

VF3 = UUID("00000000-0000-0000-0000-000000000003")
VF5 = UUID("00000000-0000-0000-0000-000000000005")
EVO = UUID("00000000-0000-0000-0000-000000000200")
GONE = UUID("00000000-0000-0000-0000-0000000000ff")


def _car(vehicle_id: UUID, name: str, price: str, range_km: str) -> VehicleFacts:
    return VehicleFacts(
        vehicle_id=vehicle_id,
        display_name=name,
        vehicle_type=VehicleType.CAR,
        starting_price_vnd=Decimal(price),
        specs={
            "range_km": range_km,
            "seat_count": 5,
            "battery_capacity_kwh": "37.23",
            "body_type": "SUV",
            "torque_nm": None,
        },
    )


def _motorbike(vehicle_id: UUID, name: str) -> VehicleFacts:
    return VehicleFacts(
        vehicle_id=vehicle_id,
        display_name=name,
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        starting_price_vnd=Decimal("22000000"),
        specs={"range_max_km": "203", "max_load_kg": "150", "battery_type": "LFP"},
    )


def test_two_valid_ids_return_every_field_the_client_needs() -> None:
    result = compare_vehicles(
        [str(VF3), str(VF5)],
        facts=[
            _car(VF3, "VinFast VF 3 All New", "299000000", "210"),
            _car(VF5, "VinFast VF 5 All New", "529000000", "326"),
        ],
        image_urls={VF3: "https://catalog.example/vf3.png"},
    )

    first, second = result.vehicles
    assert [item.found for item in result.vehicles] == [True, True]
    assert first.name == "VinFast VF 3 All New"
    assert first.price_vnd == "299000000"
    assert first.image_url == "https://catalog.example/vf3.png"
    assert first.specs["range_km"] == "210"
    # Xe không có ảnh vẫn là một cột hợp lệ — thiếu ảnh không phải thiếu xe.
    assert second.image_url is None
    # Cột `None` trong specs bị bỏ hẳn thay vì mang chuỗi rỗng.
    assert "torque_nm" not in first.specs
    # Bộ tiêu chí chỉ giữ dòng có ít nhất một xe có dữ liệu.
    assert [code for code, _ in result.spec_fields] == [
        "range_km",
        "battery_capacity_kwh",
        "seat_count",
        "body_type",
    ]


def test_an_unknown_id_is_reported_in_place_and_never_raises() -> None:
    result = compare_vehicles(
        [str(VF3), str(GONE)],
        facts=[_car(VF3, "VinFast VF 3 All New", "299000000", "210")],
    )

    assert [item.found for item in result.vehicles] == [True, False]
    assert result.missing_vehicle_ids == (str(GONE),)
    # Cột thiếu không được mang dữ liệu bịa của cột bên cạnh.
    assert result.vehicles[1].name == ""
    assert result.vehicles[1].specs == {}
    # Bảng vẫn dựng được từ xe còn lại.
    assert result.found_vehicles[0].name == "VinFast VF 3 All New"


def test_a_car_and_a_motorbike_share_one_merged_criteria_set() -> None:
    """P-150 bán cả hai dòng nên "so sánh vf3 với evo200" là câu hỏi hợp lệ."""

    result = compare_vehicles(
        [str(VF3), str(EVO)],
        facts=[
            _car(VF3, "VinFast VF 3 All New", "299000000", "210"),
            _motorbike(EVO, "VinFast Evo 200 Kèm Pin"),
        ],
    )

    codes = [code for code, _ in result.spec_fields]
    assert result.is_cross_type is True
    assert "range_km" in codes and "range_max_km" in codes
    # Dòng không xe nào có dữ liệu bị loại khỏi bảng trộn loại.
    assert "charging_time_minutes" not in codes


def test_so_thap_phan_cua_cot_numeric_khong_loi_so_khong_thua() -> None:
    # Prod (probe V2-26): bảng in "215.00" / "18.640" — số thô của numeric.
    result = compare_vehicles(
        [str(VF3)],
        facts=[
            VehicleFacts(
                vehicle_id=VF3,
                display_name="VinFast VF 3 All New",
                vehicle_type=VehicleType.CAR,
                starting_price_vnd=Decimal("299000000"),
                specs={"range_km": Decimal("215.00"), "battery_capacity_kwh": Decimal("18.640"), "seat_count": 4},
            )
        ],
        image_urls={},
    )
    specs = result.vehicles[0].specs
    assert specs["range_km"] == "215"
    assert specs["battery_capacity_kwh"] == "18,64"
    assert specs["seat_count"] == "4"
