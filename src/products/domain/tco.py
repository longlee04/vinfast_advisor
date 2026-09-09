"""Công thức tổng chi phí sở hữu, thuần tính toán.

Không chạm database và không biết HTTP, nên kiểm thử được bằng vector tính
tay. Mọi số tiền là `Decimal`: đây là chi phí sở hữu một tài sản vài trăm
triệu đồng, sai số dấu phẩy động của `float` không có chỗ ở đây.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

MONTHS_PER_YEAR: Final[int] = 12
SEVEN_YEARS_IN_MONTHS: Final[int] = 84
KM_PER_CONSUMPTION_UNIT: Final[Decimal] = Decimal("100")


#: Hai tỉnh/thành thuộc Khu vực I của biểu lệ phí đăng ký biển số.
#:
#: [GIẢ ĐỊNH] Đúng hai mức theo Thông tư 155/2025/TT-BTC, dùng tên tỉnh sau sáp
#: nhập 2025. Có thêm mức thì THÊM giá trị vùng + dòng dữ liệu, không sửa công
#: thức — `calculate_tco` chỉ nhận `plate_fee_vnd` đã resolve, nó không biết vùng.
KHU_VUC_I_PROVINCES: Final[frozenset[str]] = frozenset({"Hà Nội", "Hồ Chí Minh"})

KHU_VUC_I: Final[str] = "KHU_VUC_I"
KHU_VUC_II: Final[str] = "KHU_VUC_II"


def resolve_region_code(province: str) -> str:
    """Ánh xạ tỉnh khách chọn sang mã vùng lệ phí biển số.

    Tỉnh không khớp `KHU_VUC_I_PROVINCES` rơi về `KHU_VUC_II` và KHÔNG raise:
    validate tên tỉnh hợp lệ là việc của tầng trích slot phía trên, không phải
    của một hàm thuần. Mặc định về Khu vực II cũng là chiều đúng về nghiệp vụ —
    đa số tỉnh/thành thuộc nhóm đó.
    """

    return KHU_VUC_I if province.strip() in KHU_VUC_I_PROVINCES else KHU_VUC_II


def _money(value: Decimal) -> Decimal:
    """Làm tròn về đồng, nửa lên."""
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class TcoInput:
    """Mọi số liệu cần để tính, đã được tầng trên resolve xong."""

    vehicle_price_vnd: Decimal
    monthly_km: Decimal
    years: int
    kwh_per_100km: Decimal
    electricity_vnd_per_kwh: Decimal
    registration_fee_percent: Decimal
    registration_fee_flat_vnd: Decimal
    plate_fee_vnd: Decimal
    inspection_fee_vnd: Decimal
    inspection_first_month: int
    inspection_interval_months: int
    inspection_interval_months_after_7y: int
    insurance_vnd_per_year: Decimal
    road_fee_vnd_per_year: Decimal
    maintenance_vnd_per_service: Decimal
    maintenance_interval_km: Decimal


@dataclass(frozen=True, slots=True)
class TcoBreakdown:
    """Từng khoản chi phí, kèm số lần cho hai khoản lặp lại."""

    vehicle_price_vnd: Decimal
    registration_fee_vnd: Decimal
    plate_fee_vnd: Decimal
    inspection_vnd: Decimal
    inspection_count: int
    insurance_vnd: Decimal
    road_fee_vnd: Decimal
    electricity_vnd: Decimal
    maintenance_vnd: Decimal
    maintenance_count: int
    total_km: Decimal
    total_upfront_vnd: Decimal
    total_ownership_vnd: Decimal


def count_inspections(*, months: int, first_month: int, interval_months: int, interval_after_7y: int) -> int:
    """Đếm số lần đăng kiểm rơi vào khoảng sở hữu.

    `first_month = 0` nghĩa là estimate hiện tại chưa tính khoản kiểm định cho
    loại xe đó. Đây là trạng thái dữ liệu, không phải tuyên bố miễn trừ pháp lý.
    """
    if first_month <= 0 or interval_months <= 0:
        return 0
    count = 0
    month = first_month
    while month <= months:
        count += 1
        # Tại đúng 7 năm xe vẫn thuộc nhóm "đến 07 năm"; chu kỳ 12 tháng
        # chỉ bắt đầu khi tuổi xe đã trên 7 năm.
        step = interval_after_7y if month > SEVEN_YEARS_IN_MONTHS else interval_months
        if step <= 0:
            break
        month += step
    return count


def derive_consumption(
    *,
    published_kwh_per_100km: Decimal | None,
    battery_capacity_kwh: Decimal | None,
    range_km: Decimal | None,
) -> Decimal | None:
    """Trả mức tiêu thụ, ưu tiên số công bố.

    Khi không có số công bố, suy từ dung lượng pin chia quãng đường. Trả `None`
    khi không đủ dữ liệu — người gọi phải báo không tính được, không được đoán.
    """
    if published_kwh_per_100km is not None and published_kwh_per_100km > 0:
        return published_kwh_per_100km
    if battery_capacity_kwh is None or range_km is None or range_km <= 0:
        return None
    derived = battery_capacity_kwh / range_km * KM_PER_CONSUMPTION_UNIT
    return derived.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def calculate_tco(data: TcoInput) -> TcoBreakdown:
    """Ghép các khoản thành tổng chi phí sở hữu."""
    months = data.years * MONTHS_PER_YEAR
    total_km = data.monthly_km * months

    electricity = _money(total_km / KM_PER_CONSUMPTION_UNIT * data.kwh_per_100km * data.electricity_vnd_per_kwh)
    registration_fee = _money(
        data.vehicle_price_vnd * data.registration_fee_percent / Decimal("100") + data.registration_fee_flat_vnd
    )
    insurance = _money(data.insurance_vnd_per_year * data.years)
    road_fee = _money(data.road_fee_vnd_per_year * data.years)

    # Làm tròn lên: đi quá mốc một kilômét vẫn phải vào xưởng.
    maintenance_count = 0
    if data.maintenance_interval_km > 0:
        maintenance_count = int((total_km / data.maintenance_interval_km).to_integral_value(rounding="ROUND_CEILING"))
    maintenance = _money(data.maintenance_vnd_per_service * maintenance_count)

    inspection_count = count_inspections(
        months=months,
        first_month=data.inspection_first_month,
        interval_months=data.inspection_interval_months,
        interval_after_7y=data.inspection_interval_months_after_7y,
    )
    inspection = _money(data.inspection_fee_vnd * inspection_count)

    total_upfront = _money(data.vehicle_price_vnd + registration_fee + data.plate_fee_vnd)
    total_ownership = _money(total_upfront + electricity + insurance + road_fee + maintenance + inspection)

    return TcoBreakdown(
        vehicle_price_vnd=_money(data.vehicle_price_vnd),
        registration_fee_vnd=registration_fee,
        plate_fee_vnd=_money(data.plate_fee_vnd),
        inspection_vnd=inspection,
        inspection_count=inspection_count,
        insurance_vnd=insurance,
        road_fee_vnd=road_fee,
        electricity_vnd=electricity,
        maintenance_vnd=maintenance,
        maintenance_count=maintenance_count,
        total_km=total_km,
        total_upfront_vnd=total_upfront,
        total_ownership_vnd=total_ownership,
    )
