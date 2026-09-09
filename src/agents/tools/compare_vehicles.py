"""[COMPARE_VEHICLES] Tool ghép bảng so sánh — tất định, không văn xuôi, không LLM.

**Rủi ro: nhóm tra cứu catalog tất định, auto-approve, KHÔNG qua HITL.** Cùng
nhóm với `CATALOG_BROWSE` và `ON_ROAD_PRICE_LOOKUP` (`domain/quote_risk.py`):
mọi con số ở đây chép nguyên văn từ `vehicles`/`vehicle_prices`/bảng specs, không
có bước cá nhân hoá, không có thương lượng, không có cam kết tài chính. Vì vậy
nhánh này KHÔNG chạm vào máy trạng thái HITL (`AI → PENDING_HANDOFF → HUMAN`).

**Vì sao tool không tự truy vấn database.** `tools/` trong repo này là tầng tính
toán thuần (`tools/tco.py`, `tools/on_road_price.py` đều vậy): mọi I/O nằm ở
`services/`. Giữ đúng ranh giới đó cho phép test toàn bộ luật "thiếu xe thì báo
thiếu" mà không cần Postgres, và đó chính là thứ đặc tả muốn khi nói "giữ tool
tầng dưới thuần deterministic, dễ test". `vehicle_ids` vẫn là tham số ĐẦU TIÊN và
là thứ quyết định hình dạng kết quả — service chỉ đưa thêm dữ liệu đã đọc sẵn.

**Không ném exception khi thiếu xe.** Một `vehicle_id` không có trong catalog trở
thành một phần tử `found=False` trong payload. Ném lỗi ở đây sẽ giết cả lượt của
khách vì một mẫu xe vừa bị gỡ khỏi danh mục — trong khi câu trả lời đúng là
"mẫu này em chưa tìm thấy, còn hai mẫu kia thì đây ạ".

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from src.agents.contracts import VehicleFacts

#: Thông số đưa vào bảng so sánh, theo thứ tự hiển thị, cho từng loại xe.
#:
#: Khoá là tên cột như `adapters/catalog_reader._car_specs` /`_motorbike_specs`
#: đặt — chép sang một bộ tên riêng ở đây là dựng nguồn sự thật thứ hai, và lần
#: đổi cột tiếp theo sẽ làm bảng so sánh im lặng rỗng đi một dòng.
#:
#: [GIẢ ĐỊNH] Bộ tiêu chí và nhãn tiếng Việt dưới đây chọn theo thứ khách hay
#: hỏi nhất khi cân nhắc giữa hai xe (tầm chạy, pin, công suất, sạc). Không có
#: tài liệu nghiệp vụ nào chốt danh sách này; đổi nó là đổi bảng, không đổi luật.
CAR_SPEC_FIELDS: tuple[tuple[str, str], ...] = (
    ("range_km", "Tầm hoạt động (km)"),
    ("battery_capacity_kwh", "Dung lượng pin (kWh)"),
    ("motor_power_kw", "Công suất (kW)"),
    ("torque_nm", "Mô-men xoắn (Nm)"),
    ("seat_count", "Số chỗ ngồi"),
    ("max_speed_kmh", "Tốc độ tối đa (km/h)"),
    ("acceleration_0_100_seconds", "Tăng tốc 0–100 km/h (giây)"),
    ("fast_charge_time_minutes", "Sạc nhanh (phút)"),
    ("cargo_volume_standard_l", "Khoang hành lý (lít)"),
    ("body_type", "Kiểu dáng"),
)
MOTORBIKE_SPEC_FIELDS: tuple[tuple[str, str], ...] = (
    ("range_max_km", "Tầm hoạt động (km)"),
    ("battery_capacity_kwh", "Dung lượng pin (kWh)"),
    ("battery_type", "Loại pin"),
    ("motor_power_w", "Công suất (W)"),
    ("torque_nm", "Mô-men xoắn (Nm)"),
    ("max_speed_kmh", "Tốc độ tối đa (km/h)"),
    ("max_load_kg", "Tải trọng tối đa (kg)"),
    ("charging_time_minutes", "Thời gian sạc (phút)"),
    ("seat_height_mm", "Chiều cao yên (mm)"),
    ("license_requirement", "Yêu cầu bằng lái"),
)


@dataclass(frozen=True, slots=True)
class ComparedVehicle:
    """Một cột của bảng so sánh. `found=False` thì mọi field còn lại vô nghĩa."""

    vehicle_id: str
    found: bool
    name: str = ""
    vehicle_type: str = ""
    image_url: str | None = None
    #: Giá niêm yết dạng chuỗi số nguyên VND, hoặc `None` khi chưa có giá hiệu
    #: lực. CHUỖI chứ không phải số: cùng quy ước với
    #: `contracts.VehiclePitch.starting_price_vnd`, để JSON không làm tròn nhị
    #: phân một con số hàng trăm triệu.
    price_vnd: str | None = None
    #: `mã cột` → giá trị đã thành chuỗi. Cột thiếu dữ liệu bị bỏ hẳn khỏi dict
    #: thay vì mang giá trị rỗng: "chưa có dữ liệu" là việc của tầng hiển thị nói.
    specs: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VehicleComparison:
    """Kết quả tool: các cột xe + bộ tiêu chí đã dùng, KHÔNG kèm câu chữ.

    Cố ý không có field `answer`/`summary`: đặc tả yêu cầu tool trả payload có
    cấu trúc và để tầng trả lời tự viết. Nhét câu chữ vào đây sẽ khiến bảng và
    đoạn tóm tắt dính chặt nhau, và mỗi lần đổi giọng văn lại phải sửa tool.
    """

    vehicles: tuple[ComparedVehicle, ...]
    #: `(mã cột, nhãn tiếng Việt)` theo đúng thứ tự trình bày.
    spec_fields: tuple[tuple[str, str], ...] = ()

    @property
    def found_vehicles(self) -> tuple[ComparedVehicle, ...]:
        return tuple(item for item in self.vehicles if item.found)

    @property
    def missing_vehicle_ids(self) -> tuple[str, ...]:
        return tuple(item.vehicle_id for item in self.vehicles if not item.found)

    @property
    def is_cross_type(self) -> bool:
        """Bảng có trộn ô tô với xe máy điện không.

        KHÔNG phải điều kiện từ chối. P-150 bán cả hai dòng và "so sánh vf3 với
        evo200" là một câu hỏi hợp lệ của khách; điều duy nhất phải làm là chọn
        bộ tiêu chí chung thay vì bộ riêng của một loại. Đây là điểm khác có chủ
        đích so với `domain/comparison.compare_candidates` (A5-4), nơi bảng gửi
        TƯ VẤN VIÊN từ chối trộn loại vì nó xếp hạng "xe nào tốt hơn" theo từng
        tiêu chí — xếp hạng giữa hai loại phương tiện thì vô nghĩa, còn đặt cạnh
        nhau để khách tự đọc thì không.
        """

        return len({item.vehicle_type for item in self.found_vehicles}) > 1


def compare_vehicles(
    vehicle_ids: Sequence[str],
    *,
    facts: Sequence[VehicleFacts] = (),
    image_urls: Mapping[UUID, str] | None = None,
) -> VehicleComparison:
    """Ghép payload so sánh cho đúng `vehicle_ids`, theo đúng thứ tự đã truyền.

    Thứ tự được giữ nguyên vì nó là thứ tự khách nêu trong câu, và bảng đảo cột
    so với câu hỏi là bảng khó đọc.

    Một `vehicle_id` không có `VehicleFacts` tương ứng → `found=False`. Không
    raise: xem docstring module.
    """

    images = dict(image_urls or {})
    facts_by_id = {str(item.vehicle_id): item for item in facts}
    columns = tuple(
        _column(vehicle_id, facts_by_id.get(vehicle_id), images) for vehicle_id in dict.fromkeys(vehicle_ids)
    )
    return VehicleComparison(vehicles=columns, spec_fields=_spec_fields_for(columns))


def _column(
    vehicle_id: str,
    facts: VehicleFacts | None,
    images: Mapping[UUID, str],
) -> ComparedVehicle:
    if facts is None:
        return ComparedVehicle(vehicle_id=vehicle_id, found=False)
    return ComparedVehicle(
        vehicle_id=vehicle_id,
        found=True,
        name=facts.display_name,
        vehicle_type=str(facts.vehicle_type),
        image_url=images.get(facts.vehicle_id),
        price_vnd=_price_text(facts.starting_price_vnd),
        specs=_specs(facts),
    )


def _spec_fields_for(
    columns: Sequence[ComparedVehicle],
) -> tuple[tuple[str, str], ...]:
    """Bộ tiêu chí của bảng: riêng theo loại khi cùng loại, hợp nhất khi trộn.

    Hợp nhất bằng cách nối hai bộ và bỏ dòng KHÔNG xe nào có dữ liệu: bảng trộn
    loại mà giữ nguyên cả hai bộ sẽ có một nửa số dòng trống hoàn toàn ở mỗi cột.
    """

    found = [item for item in columns if item.found]
    types = {item.vehicle_type for item in found}
    if types == {"CAR"}:
        candidates = CAR_SPEC_FIELDS
    elif types == {"ELECTRIC_MOTORBIKE"}:
        candidates = MOTORBIKE_SPEC_FIELDS
    else:
        seen: dict[str, str] = {}
        for code, label in (*CAR_SPEC_FIELDS, *MOTORBIKE_SPEC_FIELDS):
            seen.setdefault(code, label)
        candidates = tuple(seen.items())
    return tuple((code, label) for code, label in candidates if any(code in item.specs for item in found))


def _specs(facts: VehicleFacts) -> dict[str, str]:
    """Chỉ giữ cột CÓ giá trị, đã thành chuỗi."""

    return {code: text for code, value in facts.specs.items() if (text := _as_text(value)) is not None}


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        # "215.00" / "18.640" là số thô của cột numeric — khách đọc "215 km",
        # "18,64 kWh". Bỏ số 0 thừa, dấu phẩy thập phân kiểu Việt.
        normalized = value.normalize()
        text = format(normalized, "f") if normalized == normalized.to_integral() else format(normalized, "f").rstrip("0").rstrip(".")
        return text.replace(".", ",") or None
    text = str(value).strip()
    return text or None


def _price_text(amount: Decimal | None) -> str | None:
    """Chuỗi số nguyên VND, cùng dạng `contracts.VehiclePitch.starting_price_vnd`."""

    return None if amount is None else format(amount, "f")


__all__ = [
    "CAR_SPEC_FIELDS",
    "MOTORBIKE_SPEC_FIELDS",
    "ComparedVehicle",
    "VehicleComparison",
    "compare_vehicles",
]
