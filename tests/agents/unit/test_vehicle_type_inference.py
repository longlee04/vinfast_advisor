"""Unit tests cho vehicle_type_inference (T3) — 12 ca từ design doc Success Criteria."""

from decimal import Decimal

from src.agents.domain.values import SlotName, VehicleType
from src.agents.domain.vehicle_type_inference import infer_vehicle_type


def _slots(**values: object) -> dict[SlotName, object]:
    return {SlotName(k): v for k, v in values.items()}


class TestInferVehicleType:
    """Suy loại xe từ known_slots — 12 ca thiết kế."""

    def test_passenger_count_5_yields_car(self) -> None:
        result, inferred = infer_vehicle_type(_slots(passenger_count=5))
        assert result is VehicleType.CAR
        assert inferred is True

    def test_purpose_di_lam_alone_yields_none(self) -> None:
        result, inferred = infer_vehicle_type(_slots(purpose="đi làm"))
        assert result is None
        assert inferred is False

    def test_passenger_1_no_budget_yields_none(self) -> None:
        result, inferred = infer_vehicle_type(_slots(passenger_count=1))
        assert result is None
        assert inferred is False

    def test_passenger_2_no_budget_yields_none(self) -> None:
        result, inferred = infer_vehicle_type(_slots(passenger_count=2))
        assert result is None
        assert inferred is False

    def test_passenger_1_budget_700m_yields_car(self) -> None:
        result, inferred = infer_vehicle_type(_slots(passenger_count=1, budget_max_vnd=Decimal("700000000")))
        assert result is VehicleType.CAR
        assert inferred is True

    def test_passenger_1_budget_60m_yields_bike(self) -> None:
        result, inferred = infer_vehicle_type(_slots(passenger_count=1, budget_max_vnd=Decimal("60000000")))
        assert result is VehicleType.ELECTRIC_MOTORBIKE
        assert inferred is True

    def test_passenger_2_budget_60m_yields_bike(self) -> None:
        result, inferred = infer_vehicle_type(_slots(passenger_count=2, budget_max_vnd=Decimal("60000000")))
        assert result is VehicleType.ELECTRIC_MOTORBIKE
        assert inferred is True

    def test_passenger_2_budget_exact_100m_yields_none(self) -> None:
        # Biên là `<`, không `<=`.
        result, inferred = infer_vehicle_type(_slots(passenger_count=2, budget_max_vnd=Decimal("100000000")))
        assert result is None
        assert inferred is False

    def test_passenger_2_budget_150m_yields_none(self) -> None:
        # Vùng giữa (100tr–188tr), không sản phẩm nào vừa.
        result, inferred = infer_vehicle_type(_slots(passenger_count=2, budget_max_vnd=Decimal("150000000")))
        assert result is None
        assert inferred is False

    def test_passenger_3_budget_80m_yields_none(self) -> None:
        # Xung đột: pc>=3 → CAR nhưng ngân sách chỉ đủ xe máy.
        result, inferred = infer_vehicle_type(_slots(passenger_count=3, budget_max_vnd=Decimal("80000000")))
        assert result is None
        assert inferred is False

    def test_no_passenger_budget_60m_yields_none(self) -> None:
        # Con số nhỏ có thể là khoản trả góp hàng tháng.
        result, inferred = infer_vehicle_type(_slots(budget_max_vnd=Decimal("60000000")))
        assert result is None
        assert inferred is False

    def test_purpose_ca_nhan_alone_yields_none(self) -> None:
        # Khoá luật phủ định — không suy từ "cá nhân" sang xe máy.
        result, inferred = infer_vehicle_type(_slots(purpose="cá nhân"))
        assert result is None
        assert inferred is False

    def test_purpose_giao_hang_yields_bike(self) -> None:
        result, inferred = infer_vehicle_type(_slots(purpose="giao hàng"))
        assert result is VehicleType.ELECTRIC_MOTORBIKE
        assert inferred is True

    def test_empty_slots_yields_none(self) -> None:
        result, inferred = infer_vehicle_type({})
        assert result is None
        assert inferred is False

    def test_budget_exact_car_min_price_yields_car(self) -> None:
        # Biên `>=` của CAR_MIN_PRICE_VND (188tr): đúng ngưỡng là ô tô.
        result, inferred = infer_vehicle_type(_slots(budget_max_vnd=Decimal("188000000")))
        assert result is VehicleType.CAR
        assert inferred is True

    def test_passenger_3_without_budget_yields_car(self) -> None:
        # pc>=3 là tín hiệu đủ mạnh, không cần ngân sách.
        result, inferred = infer_vehicle_type(_slots(passenger_count=3))
        assert result is VehicleType.CAR
        assert inferred is True

    def test_passenger_3_budget_exact_car_min_price_yields_car(self) -> None:
        result, inferred = infer_vehicle_type(_slots(passenger_count=3, budget_max_vnd=Decimal("188000000")))
        assert result is VehicleType.CAR
        assert inferred is True
