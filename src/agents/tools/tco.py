"""Deterministic total-cost-of-ownership calculation for A5-5."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Final, Literal
from uuid import UUID

from src.agents.contracts import TcoResult
from src.agents.domain.values import VehicleType
from src.products.domain.tco import TcoInput, calculate_tco, derive_consumption

DAYS_PER_MONTH = Decimal("30")

#: Quãng đường mỗi ngày dùng khi khách không nói. Không phải con số tuỳ tiện: đây
#: là mức nêu trong ví dụ mẫu của câu hỏi thu thập (`prompts/combined_intake`),
#: nên phần lớn khách hoặc xác nhận nó hoặc sửa nó bằng chính con số của mình.
#:
#: Dùng mặc định thay vì trả `TCO_UNAVAILABLE` là quyết định đã đo: trên VF 8,
#: phần chi phí đổi theo quãng đường chiếm 2,4% tổng ở 20 km/ngày và 8,8% ở 80
#: km/ngày — hơn 91% con số đã biết trước khi khách nói gì. Mọi chỗ dùng nó PHẢI
#: nói ra rằng mình đang tính theo mốc này.
DEFAULT_DAILY_DISTANCE_KM: Final[float] = 30.0
HORIZON_MONTHS = 60
MONTHS_PER_YEAR = Decimal("12")
TCO_WARNING = "Đây là ước tính, không phải báo giá cuối cùng."

BatteryOwnershipModel = Literal["INCLUDED", "PURCHASE", "SUBSCRIPTION", "SWAP", "NOT_APPLICABLE"]


@dataclass(frozen=True, slots=True)
class PromotionInput:
    """Legacy Agent input retained for compatibility; stable catalog TCO ignores it."""

    promotion_id: UUID
    discount_amount_vnd: Decimal | None = None
    discount_percent: Decimal | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class BatteryPolicyInput:
    """Legacy Agent input retained for compatibility; historical policy costs are ignored."""

    ownership_model: BatteryOwnershipModel
    monthly_fee_vnd: Decimal | None = None
    purchase_price_vnd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AppliedPromotion:
    """One active promotion included in a customer-facing breakdown."""

    promotion_code: str
    title: str
    discount_vnd: Decimal
    source_url: str | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class CustomerCostBreakdown:
    """Serializable customer-facing TCO summary with a mandatory disclaimer."""

    base_price_vnd: Decimal
    battery_ownership_model: str
    battery_monthly_fee_vnd: Decimal | None
    registration_fee_vnd: Decimal
    plate_fee_vnd: Decimal
    inspection_fee_vnd: Decimal
    mandatory_insurance_year1_vnd: Decimal
    applicable_promotions: list[AppliedPromotion] = field(default_factory=list)
    total_discount_vnd: Decimal = Decimal("0")
    total_upfront_vnd: Decimal = Decimal("0")
    electricity_cost_5y_vnd: Decimal = Decimal("0")
    maintenance_cost_5y_vnd: Decimal = Decimal("0")
    road_fee_5y_vnd: Decimal = Decimal("0")
    inspection_cost_5y_vnd: Decimal = Decimal("0")
    battery_subscription_5y_vnd: Decimal | None = None
    total_5y_ownership_vnd: Decimal = Decimal("0")
    vehicle_id: UUID | None = None
    model_name: str = ""
    region_code: str = "VN"
    estimated_daily_km: Decimal = Decimal("0")
    disclaimer: str = TCO_WARNING
    source_notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.disclaimer.strip():
            raise ValueError("CustomerCostBreakdown disclaimer is required")

    def to_dict(self) -> dict:
        """Serialize Decimal, UUID, datetime, and promotion values to JSON-safe data."""

        return {
            "base_price_vnd": str(self.base_price_vnd),
            "battery_ownership_model": self.battery_ownership_model,
            "battery_monthly_fee_vnd": _optional_decimal(self.battery_monthly_fee_vnd),
            "registration_fee_vnd": str(self.registration_fee_vnd),
            "plate_fee_vnd": str(self.plate_fee_vnd),
            "inspection_fee_vnd": str(self.inspection_fee_vnd),
            "mandatory_insurance_year1_vnd": str(self.mandatory_insurance_year1_vnd),
            "applicable_promotions": [
                {
                    "promotion_code": item.promotion_code,
                    "title": item.title,
                    "discount_vnd": str(item.discount_vnd),
                    "source_url": item.source_url,
                    "valid_to": item.valid_to.isoformat() if item.valid_to else None,
                }
                for item in self.applicable_promotions
            ],
            "total_discount_vnd": str(self.total_discount_vnd),
            "total_upfront_vnd": str(self.total_upfront_vnd),
            "electricity_cost_5y_vnd": str(self.electricity_cost_5y_vnd),
            "maintenance_cost_5y_vnd": str(self.maintenance_cost_5y_vnd),
            "road_fee_5y_vnd": str(self.road_fee_5y_vnd),
            "inspection_cost_5y_vnd": str(self.inspection_cost_5y_vnd),
            "battery_subscription_5y_vnd": _optional_decimal(self.battery_subscription_5y_vnd),
            "total_5y_ownership_vnd": str(self.total_5y_ownership_vnd),
            "vehicle_id": str(self.vehicle_id) if self.vehicle_id else None,
            "model_name": self.model_name,
            "region_code": self.region_code,
            "estimated_daily_km": str(self.estimated_daily_km),
            "disclaimer": self.disclaimer,
            "source_notes": list(self.source_notes),
        }


def _optional_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


@dataclass(frozen=True, slots=True)
class TcoAssumptionInput:
    """The active Admin-approved TCO assumption set for one type and region."""

    assumption_id: UUID
    vehicle_type: VehicleType
    region_code: str
    electricity_vnd_per_kwh: Decimal
    horizon_months: int = HORIZON_MONTHS
    registration_fee_percent: Decimal | None = None
    registration_fee_flat_vnd: Decimal | None = None
    plate_fee_vnd: Decimal | None = None
    inspection_fee_vnd: Decimal | None = None
    inspection_first_month: int = 0
    inspection_interval_months: int = 0
    inspection_interval_months_after_7y: int = 0
    mandatory_insurance_vnd_per_year: Decimal | None = None
    road_fee_vnd_per_year: Decimal | None = None
    maintenance_vnd_per_service: Decimal | None = None
    maintenance_interval_km: Decimal | None = None
    source_note: str | None = None


@dataclass(frozen=True, slots=True)
class VehicleTcoInput:
    """Structured catalog values normalized before calling the canonical Product calculator."""

    vehicle_type: VehicleType
    prices_vnd: Mapping[str, Decimal]
    assumptions: tuple[TcoAssumptionInput, ...]
    battery_policy: BatteryPolicyInput
    promotions: tuple[PromotionInput, ...] = ()
    energy_consumption_kwh_per_100km: Decimal | None = None
    battery_capacity_kwh: Decimal | None = None
    battery_quantity: int | None = None
    range_max_km: Decimal | None = None


@dataclass(frozen=True, slots=True)
class TcoAssumptionLine:
    """One displayable and auditable assumption used by the calculation."""

    code: str
    value: str
    unit: str | None = None
    source_note: str | None = None


@dataclass(frozen=True, slots=True)
class DetailedTcoResult(TcoResult):
    """Contract-compatible result enriched for the TCO table and citations."""

    monthly_distance_km: Decimal | None = None
    energy_consumption_kwh_per_100km: Decimal | None = None
    energy_consumption_derived: bool = False
    assumption_lines: tuple[TcoAssumptionLine, ...] = field(default_factory=tuple)
    selected_promotion_id: UUID | None = None
    warning: str = TCO_WARNING
    breakdown_detail: dict | None = None


def _unavailable(
    *,
    vehicle_id: UUID,
    computed_at: datetime,
    reason: str,
    assumptions_id: UUID | None = None,
    monthly_distance_km: Decimal | None = None,
) -> DetailedTcoResult:
    return DetailedTcoResult(
        vehicle_id=vehicle_id,
        total_vnd=None,
        components_vnd={},
        assumptions_id=assumptions_id,
        computed_at=computed_at,
        unavailable_reason=f"TCO_UNAVAILABLE: {reason}",
        monthly_distance_km=monthly_distance_km,
    )


def tco_unavailable(*, vehicle_id: UUID, computed_at: datetime, reason: str) -> DetailedTcoResult:
    """Build a standard unavailable result for failures before catalog data is loaded."""

    return _unavailable(vehicle_id=vehicle_id, computed_at=computed_at, reason=reason)


def _require_non_negative(name: str, value: Decimal | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative")


#: Hai cách sở hữu pin mà KHÁCH chọn được, khác `BatteryOwnershipModel` (mô tả
#: chính sách của catalog).
BatteryPlan = Literal["INCLUDED", "SUBSCRIPTION"]

#: Số tháng thuê pin tính vào tổng 5 năm — đúng bằng chân trời của cả phép tính.
BATTERY_SUBSCRIPTION_MONTHS: Final[int] = HORIZON_MONTHS


def _purchase_price(data: VehicleTcoInput, battery_plan: BatteryPlan = "INCLUDED") -> tuple[Decimal | None, str | None]:
    """Giá xe theo cách sở hữu pin khách chọn.

    Gói THUÊ PIN dùng giá riêng của nó, KHÔNG dùng giá xe kèm pin: hai con số
    khác nhau trong catalog (VF 6 Eco: 646.000.000 kèm pin so với 689.050.000
    gói thuê). Lấy giá kèm pin rồi cộng thêm phí thuê là tính hai lần phần pin.
    Thiếu giá gói thuê thì trả LỖI chứ không lặng lẽ rơi về giá kia — im lặng ở
    đây là báo cho khách một con số của một sản phẩm khác.
    """

    if battery_plan == "SUBSCRIPTION":
        price = data.prices_vnd.get("BATTERY_SUBSCRIPTION")
        if price is None:
            return None, "BATTERY_SUBSCRIPTION"
        _require_non_negative("BATTERY_SUBSCRIPTION", price)
        return price, None
    listed: Decimal | None = None
    for price_type in ("BATTERY_INCLUDED", "BATTERY_INCLUDED_PRICE", "STARTING_PRICE"):
        price = data.prices_vnd.get(price_type)
        if price is not None:
            _require_non_negative(price_type, price)
            listed = price
            break
    if listed is None:
        return None, "BATTERY_INCLUDED or STARTING_PRICE"
    # GIÁ KHUYẾN MÃI của catalog thắng giá niêm yết — nhưng chỉ khi nó thật sự
    # THẤP HƠN.
    #
    # Đo trên prod 2026-08-27: 8 dòng `PROMOTION_PRICE` ACTIVE (Klara Neo
    # 36.000.000 → 28.800.000, Vero X 34.900.000 → 32.108.000…) chưa bao giờ tới
    # tay khách, vì danh sách ưu tiên giá không có mã này. Khách nhận giá niêm
    # yết trong khi hãng đang bán rẻ hơn.
    #
    # Chốt "chỉ khi thấp hơn" là điều kiện an toàn, không phải phòng xa thừa: một
    # dòng khuyến mãi cao hơn giá niêm yết là dữ liệu hỏng, và nó sẽ làm khách
    # phải trả nhiều hơn vì có khuyến mãi. Khác `discount_vnd` — ưu đãi tư vấn
    # viên cấp — chỗ này là giá NIÊM YẾT thứ hai của chính catalog, nên hai thứ
    # cộng dồn được: giá khuyến mãi làm nền, ưu đãi trừ tiếp.
    promotion = data.prices_vnd.get("PROMOTION_PRICE")
    if promotion is not None:
        _require_non_negative("PROMOTION_PRICE", promotion)
        if promotion < listed:
            return promotion, None
    return listed, None


def _battery_cost(data: VehicleTcoInput, battery_plan: BatteryPlan) -> Decimal:
    """Tiền pin trong 5 năm.

    Xe bán KÈM pin thì bằng 0 — không phải chỗ chưa làm xong, mà vì tiền pin đã
    nằm trong giá xe. Gói THUÊ thì là phí tháng nhân đúng chân trời của phép
    tính; thiếu phí tháng thì bằng 0 và `_purchase_price` đã chặn từ trước bằng
    cách đòi cho được giá gói thuê.
    """

    if battery_plan != "SUBSCRIPTION":
        return Decimal("0")
    monthly = data.battery_policy.monthly_fee_vnd
    if monthly is None:
        return Decimal("0")
    _require_non_negative("battery_monthly_fee_vnd", monthly)
    return monthly * BATTERY_SUBSCRIPTION_MONTHS


def _energy_consumption(data: VehicleTcoInput) -> tuple[Decimal | None, bool, str | None]:
    direct = data.energy_consumption_kwh_per_100km
    if direct is not None:
        if direct <= 0:
            return None, False, "energy_consumption_kwh_per_100km must be positive"
        return direct, False, None
    if data.vehicle_type == VehicleType.CAR:
        return None, False, "energy_consumption_kwh_per_100km"
    consumption = derive_consumption(
        published_kwh_per_100km=None,
        battery_capacity_kwh=data.battery_capacity_kwh,
        range_km=data.range_max_km,
    )
    if consumption is not None:
        return consumption, True, None
    missing = [
        name
        for name, value in (
            ("battery_capacity_kwh", data.battery_capacity_kwh),
            ("range_max_km", data.range_max_km),
        )
        if value is None
    ]
    if data.range_max_km is not None and data.range_max_km <= 0:
        missing.append("range_max_km")
    return None, False, ", ".join(missing or ["motorbike energy derivation fields"])


def _assumption_lines(
    *,
    assumption: TcoAssumptionInput,
    daily_distance_km: Decimal,
    monthly_distance_km: Decimal,
    consumption: Decimal,
    consumption_derived: bool,
) -> tuple[TcoAssumptionLine, ...]:
    return (
        TcoAssumptionLine("daily_distance_km", str(daily_distance_km), "km/day"),
        TcoAssumptionLine("days_per_month", str(DAYS_PER_MONTH), "days/month"),
        TcoAssumptionLine("monthly_distance_km", str(monthly_distance_km), "km/month"),
        TcoAssumptionLine("horizon_months", str(assumption.horizon_months), "months"),
        TcoAssumptionLine(
            "energy_consumption_kwh_per_100km",
            str(consumption),
            "kWh/100km",
            "derived" if consumption_derived else "catalog",
        ),
        TcoAssumptionLine(
            "electricity_vnd_per_kwh",
            str(assumption.electricity_vnd_per_kwh),
            "VND/kWh",
            assumption.source_note,
        ),
        # Hai dòng bảo dưỡng: client tính lại tổng tại chỗ khi khách kéo số km
        # (thẻ TCO của lõi v2) cần ĐƠN GIÁ và MỐC, không phải con số 5 năm đã
        # cộng sẵn — từ tổng thì không tách ngược ra được.
        TcoAssumptionLine("maintenance_vnd_per_service", str(assumption.maintenance_vnd_per_service or 0), "VND/lần"),
        TcoAssumptionLine("maintenance_interval_km", str(assumption.maintenance_interval_km or 0), "km"),
    )


def vinfast_tco_v1(
    *,
    vehicle_id: UUID,
    daily_distance_km: Decimal,
    data: VehicleTcoInput,
    computed_at: datetime,
    battery_plan: BatteryPlan = "INCLUDED",
    discount_vnd: Decimal = Decimal("0"),
) -> DetailedTcoResult:
    """Calculate a reproducible 60-month TCO using structured catalog data only.

    `battery_plan` là lựa chọn của KHÁCH, không phải chính sách catalog: cùng một
    chiếc xe có thể mua kèm pin hoặc thuê pin, và hai đường ra hai con số khác
    hẳn (VF 6: giá xe lệch 43 triệu, cộng thêm 84 triệu phí thuê trong 5 năm).
    Mặc định `INCLUDED` nên mọi lời gọi cũ giữ nguyên hành vi.

    `discount_vnd` trừ vào GIÁ XE, không trừ vào tổng (Sếp 2026-08-27): ưu đãi
    hiện tại của VinFast chỉ giảm giá bán. Kéo theo lệ phí trước bạ — vốn tính
    theo phần trăm giá xe — cũng giảm, và đó là đúng thực tế chứ không phải hiệu
    ứng phụ ngoài ý muốn. Mặc định 0 nên mọi lời gọi cũ không đổi một đồng nào."""

    if daily_distance_km < 0:
        raise ValueError("daily_distance_km must be non-negative")
    monthly_distance_km = daily_distance_km * DAYS_PER_MONTH
    if len(data.assumptions) != 1:
        return _unavailable(
            vehicle_id=vehicle_id,
            computed_at=computed_at,
            reason=f"expected exactly one ACTIVE tco_assumptions row, got {len(data.assumptions)}",
            monthly_distance_km=monthly_distance_km,
        )
    assumption = data.assumptions[0]
    if assumption.vehicle_type != data.vehicle_type:
        return _unavailable(
            vehicle_id=vehicle_id,
            computed_at=computed_at,
            reason="tco_assumptions.vehicle_type",
            assumptions_id=assumption.assumption_id,
            monthly_distance_km=monthly_distance_km,
        )
    if assumption.horizon_months != HORIZON_MONTHS:
        return _unavailable(
            vehicle_id=vehicle_id,
            computed_at=computed_at,
            reason=f"horizon_months must equal {HORIZON_MONTHS}",
            assumptions_id=assumption.assumption_id,
            monthly_distance_km=monthly_distance_km,
        )
    _require_non_negative("electricity_vnd_per_kwh", assumption.electricity_vnd_per_kwh)

    base_price, missing_price = _purchase_price(data, battery_plan)
    if base_price is not None and discount_vnd > 0:
        _require_non_negative("discount_vnd", discount_vnd)
        # Sàn là 0: một ưu đãi lớn hơn giá xe vẫn là ưu đãi hợp lệ (gộp nhiều
        # chương trình), nhưng một chiếc xe giá âm thì không.
        base_price = base_price - discount_vnd if discount_vnd < base_price else Decimal("0")
    if base_price is None:
        return _unavailable(
            vehicle_id=vehicle_id,
            computed_at=computed_at,
            reason=f"vehicle_prices.{missing_price}",
            assumptions_id=assumption.assumption_id,
            monthly_distance_km=monthly_distance_km,
        )
    consumption, consumption_derived, consumption_error = _energy_consumption(data)
    if consumption is None:
        return _unavailable(
            vehicle_id=vehicle_id,
            computed_at=computed_at,
            reason=consumption_error or "energy consumption",
            assumptions_id=assumption.assumption_id,
            monthly_distance_km=monthly_distance_km,
        )

    maintenance_cost = assumption.maintenance_vnd_per_service
    maintenance_interval = assumption.maintenance_interval_km
    if maintenance_cost is None and maintenance_interval is not None:
        return _unavailable(
            vehicle_id=vehicle_id,
            computed_at=computed_at,
            reason="maintenance_vnd_per_service",
            assumptions_id=assumption.assumption_id,
            monthly_distance_km=monthly_distance_km,
        )
    if maintenance_cost is not None and (maintenance_interval is None or maintenance_interval <= 0):
        return _unavailable(
            vehicle_id=vehicle_id,
            computed_at=computed_at,
            reason="maintenance_interval_km",
            assumptions_id=assumption.assumption_id,
            monthly_distance_km=monthly_distance_km,
        )
    for name, value in (
        ("registration_fee_percent", assumption.registration_fee_percent),
        ("registration_fee_flat_vnd", assumption.registration_fee_flat_vnd),
        ("plate_fee_vnd", assumption.plate_fee_vnd),
        ("inspection_fee_vnd", assumption.inspection_fee_vnd),
        ("mandatory_insurance_vnd_per_year", assumption.mandatory_insurance_vnd_per_year),
        ("road_fee_vnd_per_year", assumption.road_fee_vnd_per_year),
        ("maintenance_vnd_per_service", maintenance_cost),
    ):
        _require_non_negative(name, value)

    breakdown = calculate_tco(
        TcoInput(
            vehicle_price_vnd=base_price,
            monthly_km=monthly_distance_km,
            years=HORIZON_MONTHS // int(MONTHS_PER_YEAR),
            kwh_per_100km=consumption,
            electricity_vnd_per_kwh=assumption.electricity_vnd_per_kwh,
            registration_fee_percent=assumption.registration_fee_percent or Decimal("0"),
            registration_fee_flat_vnd=assumption.registration_fee_flat_vnd or Decimal("0"),
            plate_fee_vnd=assumption.plate_fee_vnd or Decimal("0"),
            inspection_fee_vnd=assumption.inspection_fee_vnd or Decimal("0"),
            inspection_first_month=assumption.inspection_first_month,
            inspection_interval_months=assumption.inspection_interval_months,
            inspection_interval_months_after_7y=(assumption.inspection_interval_months_after_7y),
            insurance_vnd_per_year=(assumption.mandatory_insurance_vnd_per_year or Decimal("0")),
            road_fee_vnd_per_year=assumption.road_fee_vnd_per_year or Decimal("0"),
            maintenance_vnd_per_service=maintenance_cost or Decimal("0"),
            maintenance_interval_km=maintenance_interval or Decimal("0"),
        )
    )

    rolling_fees_vnd = sum(
        (
            breakdown.registration_fee_vnd,
            breakdown.plate_fee_vnd,
            breakdown.inspection_vnd,
            breakdown.insurance_vnd,
            breakdown.road_fee_vnd,
        ),
        start=Decimal("0"),
    )

    components = {
        "promoted_purchase_price_vnd": breakdown.vehicle_price_vnd,
        "rolling_fees_vnd": rolling_fees_vnd,
        "energy_vnd": breakdown.electricity_vnd,
        "battery_vnd": _battery_cost(data, battery_plan),
        "scheduled_maintenance_vnd": breakdown.maintenance_vnd,
    }
    customer_breakdown = CustomerCostBreakdown(
        base_price_vnd=breakdown.vehicle_price_vnd,
        battery_ownership_model=data.battery_policy.ownership_model,
        battery_monthly_fee_vnd=data.battery_policy.monthly_fee_vnd,
        registration_fee_vnd=breakdown.registration_fee_vnd,
        plate_fee_vnd=breakdown.plate_fee_vnd,
        inspection_fee_vnd=breakdown.inspection_vnd,
        mandatory_insurance_year1_vnd=assumption.mandatory_insurance_vnd_per_year or Decimal("0"),
        total_upfront_vnd=(
            breakdown.vehicle_price_vnd
            + breakdown.registration_fee_vnd
            + breakdown.plate_fee_vnd
            + breakdown.inspection_vnd
            + breakdown.insurance_vnd
        ),
        electricity_cost_5y_vnd=breakdown.electricity_vnd,
        maintenance_cost_5y_vnd=breakdown.maintenance_vnd,
        road_fee_5y_vnd=breakdown.road_fee_vnd,
        inspection_cost_5y_vnd=breakdown.inspection_vnd,
        battery_subscription_5y_vnd=(components["battery_vnd"] or None),
        total_discount_vnd=discount_vnd,
        total_5y_ownership_vnd=sum(components.values(), start=Decimal("0")),
        vehicle_id=vehicle_id,
        region_code=assumption.region_code,
        estimated_daily_km=daily_distance_km,
        source_notes=[assumption.source_note] if assumption.source_note else [],
    )
    return DetailedTcoResult(
        vehicle_id=vehicle_id,
        total_vnd=sum(components.values(), start=Decimal("0")),
        components_vnd=components,
        assumptions_id=assumption.assumption_id,
        computed_at=computed_at,
        monthly_distance_km=monthly_distance_km,
        energy_consumption_kwh_per_100km=consumption,
        energy_consumption_derived=consumption_derived,
        assumption_lines=_assumption_lines(
            assumption=assumption,
            daily_distance_km=daily_distance_km,
            monthly_distance_km=monthly_distance_km,
            consumption=consumption,
            consumption_derived=consumption_derived,
        ),
        selected_promotion_id=None,
        breakdown_detail=customer_breakdown.to_dict(),
    )
