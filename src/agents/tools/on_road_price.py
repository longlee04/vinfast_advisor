"""[A7-9] Công thức giá lăn bánh — thuần tính toán, không chạm database.

Tool RIÊNG, không gộp vào tool TCO dù hai bên dùng chung bảng giả định phí: gộp
lại thì log và trace không phân biệt được lượt nào tính giá lăn bánh, lượt nào
ước tính chi phí sở hữu, mà đó đúng là thứ cần tách khi soát lại một con số đã
gửi cho khách.

Mọi số tiền là `Decimal` — cùng lý do với `src/products/domain/tco.py`: đây là
tiền của một tài sản vài trăm triệu, sai số `float` không có chỗ ở đây.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

#: Mã vùng của dòng giả định dùng chung toàn quốc trong `tco_assumptions`.
NATIONAL_REGION_CODE: Final[str] = "VN"


def _money(value: Decimal) -> Decimal:
    """Làm tròn về đồng, nửa lên — cùng quy ước với `products.domain.tco`."""

    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class OnRoadFeeAssumptions:
    """Biểu phí đã resolve cho một loại xe tại một vùng."""

    region_code: str
    registration_fee_percent: Decimal
    registration_fee_flat_vnd: Decimal
    plate_fee_vnd: Decimal
    mandatory_insurance_vnd_per_year: Decimal


@dataclass(frozen=True, slots=True)
class OnRoadPriceBreakdown:
    """Từng khoản cấu thành giá lăn bánh, cộng lại đúng bằng `total_vnd`."""

    listed_price_vnd: Decimal
    registration_fee_vnd: Decimal
    plate_fee_vnd: Decimal
    mandatory_insurance_vnd: Decimal
    total_vnd: Decimal
    province: str
    #: Biểu phí dùng để tính là của ĐÚNG tỉnh khách hỏi, hay là biểu toàn quốc.
    #: `False` nghĩa là `tco_assumptions` chưa có dòng riêng cho tỉnh đó, và câu
    #: trả lời phải nói đúng như vậy thay vì để khách tưởng số đã theo tỉnh mình.
    province_specific: bool


def vinfast_on_road_price_v1(
    *,
    listed_price_vnd: Decimal,
    province: str,
    fees: OnRoadFeeAssumptions,
) -> OnRoadPriceBreakdown:
    """Giá lăn bánh = giá niêm yết + trước bạ + biển số + bảo hiểm TNDS một năm.

    Bảo hiểm TNDS tính ĐÚNG một năm: đó là khoản bắt buộc phải đóng để xe ra
    biển, còn các năm sau thuộc chi phí sở hữu và đã nằm trong tool TCO. Cộng cả
    chu kỳ vào đây sẽ đội giá lăn bánh lên bằng một khoản khách chưa phải trả.

    Không có tham số "màu": catalog chưa có bảng phụ phí theo màu, nên màu không
    tham gia công thức [GIẢ ĐỊNH — đặc tả cho phép coi màu là optional].
    """

    for name, value in (
        ("listed_price_vnd", listed_price_vnd),
        ("registration_fee_percent", fees.registration_fee_percent),
        ("registration_fee_flat_vnd", fees.registration_fee_flat_vnd),
        ("plate_fee_vnd", fees.plate_fee_vnd),
        ("mandatory_insurance_vnd_per_year", fees.mandatory_insurance_vnd_per_year),
    ):
        if value < 0:
            raise ValueError(f"{name} must not be negative")

    registration_fee = _money(
        listed_price_vnd * fees.registration_fee_percent / Decimal("100") + fees.registration_fee_flat_vnd
    )
    plate_fee = _money(fees.plate_fee_vnd)
    insurance = _money(fees.mandatory_insurance_vnd_per_year)
    return OnRoadPriceBreakdown(
        listed_price_vnd=_money(listed_price_vnd),
        registration_fee_vnd=registration_fee,
        plate_fee_vnd=plate_fee,
        mandatory_insurance_vnd=insurance,
        total_vnd=_money(_money(listed_price_vnd) + registration_fee + plate_fee + insurance),
        province=province,
        province_specific=fees.region_code.upper() == province.upper(),
    )


__all__ = [
    "NATIONAL_REGION_CODE",
    "OnRoadFeeAssumptions",
    "OnRoadPriceBreakdown",
    "vinfast_on_road_price_v1",
]
