"""Allowlist tính năng hỏi được lượt 2 (T7) — mở rộng 2026-08-21.

3 mã gốc chốt ở T1 (BATTERY_REMOVABLE, HIGH_PAYLOAD, ANTI_THEFT). Thêm
TOWING (ô tô, 5 xe có/6 không — tách đôi tốt), BATTERY_SWAPPABLE (xe máy
điện, 15 có/22 không — tách đôi tốt) và FAST_CHARGING (ô tô, 10/10 xe có —
không tách đôi được nhưng dữ liệu XÁC THỰC, đáng xác nhận khi khách hỏi):
dữ liệu thật trong `vehicle_feature_flags` lúc rà soát 2026-08-21, trước đó
có nhưng chưa được đưa vào allowlist. `PANORAMIC_ROOF` (cửa sổ trời) KHÔNG
thêm — catalog chưa duyệt dữ liệu cho bất kỳ xe nào (0 xe có bản ghi), thêm
vào chỉ tạo allowlist trỏ tới cái không có gì để xác nhận.

2026-08-26 (nhóm C): BỎ `HIGH_PAYLOAD` — mã này có 0 cờ `YES` trên prod, hỏi
khách "có cần tải trọng lớn không" mà khách đáp "có" thì `_feature_mention_reasons`
lọc `FLAG + YES` ra rỗng: câu hỏi vô nghĩa, không cộng điểm, không lỗi. Đây là
cái bẫy "hỏi được nhưng không xe nào có" — `PANORAMIC_ROOF` đã tránh đúng cách,
`HIGH_PAYLOAD` là mã gốc T1 nên sót. Chốt chặn: `test_askable_codes_all_have_yes_flags`.

Không khớp bucket nào thì trả toàn bộ mã (dùng display_order thấp nhất ở
call-site), không trả rỗng.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from src.agents.domain.values import PurposeBucket, VehicleType

ASKABLE_FEATURES: Final[Mapping[tuple[VehicleType, PurposeBucket], frozenset[str]]] = {
    (VehicleType.CAR, PurposeBucket.FAMILY): frozenset({"ANTI_THEFT", "TOWING", "FAST_CHARGING"}),
    (VehicleType.CAR, PurposeBucket.WORK): frozenset({"ANTI_THEFT", "TOWING", "FAST_CHARGING"}),
    (VehicleType.CAR, PurposeBucket.SERVICE): frozenset({"FAST_CHARGING"}),
    # Đi tỉnh / về quê: sạc nhanh là thứ quyết định một chuyến dài, và móc kéo
    # moóc là thứ người về quê hay hỏi (chở đồ, kéo rơ-moóc nhỏ).
    (VehicleType.CAR, PurposeBucket.LONG_TRIP): frozenset({"FAST_CHARGING", "TOWING"}),
    (VehicleType.ELECTRIC_MOTORBIKE, PurposeBucket.WORK): frozenset({"BATTERY_REMOVABLE", "BATTERY_SWAPPABLE"}),
    (VehicleType.ELECTRIC_MOTORBIKE, PurposeBucket.DELIVERY): frozenset({"BATTERY_REMOVABLE", "BATTERY_SWAPPABLE"}),
    (VehicleType.ELECTRIC_MOTORBIKE, PurposeBucket.PERSONAL): frozenset({"BATTERY_REMOVABLE", "BATTERY_SWAPPABLE"}),
    # Xe máy đi đường dài sống nhờ trạm đổi pin — hết pin giữa đường tỉnh thì
    # sạc tại chỗ không phải một lựa chọn.
    (VehicleType.ELECTRIC_MOTORBIKE, PurposeBucket.LONG_TRIP): frozenset({"BATTERY_SWAPPABLE", "BATTERY_REMOVABLE"}),
}

ALL_ASKABLE: Final[frozenset[str]] = frozenset(
    {
        "BATTERY_REMOVABLE",
        "ANTI_THEFT",
        "TOWING",
        "BATTERY_SWAPPABLE",
        "FAST_CHARGING",
    }
)

#: Bug thật 2026-08-21 (Sếp báo: hỏi ô tô lại gợi ý tính năng xe máy): fallback
#: cũ dùng chung `ALL_ASKABLE` (gộp CẢ hai nhánh) cho MỌI loại xe khi bucket
#: không khớp — ô tô có mục đích rơi ngoài FAMILY/WORK/SERVICE (vd DELIVERY,
#: PERSONAL) sẽ nhận về cả `BATTERY_REMOVABLE`/`BATTERY_SWAPPABLE` (chỉ xe máy
#: điện mới có). Fallback giờ chia riêng theo loại xe — hợp toàn bộ mã đã khai
#: cho đúng loại xe đó trong `ASKABLE_FEATURES`, không lấy chéo nhánh kia.
_ALL_ASKABLE_BY_VEHICLE_TYPE: Final[Mapping[VehicleType, frozenset[str]]] = {
    vehicle_type: frozenset().union(
        *(codes for (candidate_type, _bucket), codes in ASKABLE_FEATURES.items() if candidate_type is vehicle_type)
    )
    for vehicle_type in VehicleType
}

#: Nhãn tiếng Việt của MỌI mã tính năng trong `feature_definitions`, không chỉ
#: mã hỏi được lượt 2. Mở rộng 2026-08-25 (Sếp: "tính năng đề xuất quá ít"):
#: `_feature_showcase_reasons` giờ kể mọi tính năng đã duyệt của xe, nên mã nào
#: cũng cần một nhãn người đọc được — `feature_definitions.name` không dùng thay
#: được vì chín mã đầu vẫn là tiếng Anh chưa dịch ("Anti Theft", "Battery Swappable").
#:
#: BA ràng buộc CỨNG khi viết nhãn, sai là guardrail đánh trượt cả pitch:
#: - KHÔNG chữ số — `synthesis._reject_digits_outside_placeholders` quét cả prompt,
#:   mà prompt in nguyên văn nhãn. "xe bảy chỗ" được, "xe 7 chỗ" là hỏng.
#: - KHÔNG dấu gạch dưới — `synthesis.RAW_STRUCTURED_PATTERN` chặn `[A-Za-z]+_[A-Za-z0-9_]+`.
#: - KHÔNG chứa "hỗ trợ"/"phù hợp"/"lý tưởng"/"đáp ứng" — `claim_policy.
#:   UNSTRUCTURED_CLAIM_PATTERN` chặn những cụm này trong phần văn xuôi ngoài
#:   placeholder, và LLM rất hay chép lại nguyên nhãn vào câu của nó. Vì thế
#:   `ADAS_SUITE` mang nhãn "gói ADAS giữ làn và phanh khẩn cấp" chứ không phải
#:   "gói hỗ trợ lái nâng cao" như tên trong catalog.
FEATURE_DISPLAY_LABELS: Final[Mapping[str, str]] = {
    "GPS": "định vị GPS",
    "MOBILE_APP": "ứng dụng điều khiển trên điện thoại",
    "AUTO_SHUTOFF_CHARGER": "bộ sạc tự ngắt khi đầy pin",
    "BATTERY_REMOVABLE": "pin tháo rời",
    "ANTI_THEFT": "khoá chống trộm",
    "BLUETOOTH": "kết nối Bluetooth",
    "ESIM": "eSIM kết nối dữ liệu trên xe",
    "BATTERY_SWAPPABLE": "đổi pin nhanh tại trạm",
    "TOWING": "móc kéo moóc",
    "PANORAMIC_ROOF": "cửa sổ trời toàn cảnh",
    "ADAS_SUITE": "gói ADAS giữ làn và phanh khẩn cấp",
    "7_SEATER": "xe bảy chỗ",
    "FAST_CHARGING": "sạc nhanh",
    "HIGH_RANGE_BATTERY": "pin dung lượng lớn",
    "ECO_MODE": "chế độ lái tiết kiệm",
    "COMPACT_SIZE": "thân xe nhỏ gọn",
    "HIGH_PAYLOAD": "tải trọng lớn",
    # Mười một mã thêm 2026-08-25, gắn cờ từ `vehicle_documents_car_review.csv`.
    # Nhãn viết theo lời tư vấn viên nói, không phải tên kỹ thuật: "camera quan
    # sát toàn cảnh" chứ không phải "Camera 360" (chữ số làm vỡ pitch).
    "CAMERA_360": "camera quan sát toàn cảnh",
    "BLIND_SPOT_MONITOR": "cảnh báo điểm mù",
    "ISOFIX_ANCHORS": "móc gắn ghế trẻ em ISOFIX",
    "WIRELESS_CHARGING": "sạc điện thoại không dây",
    "MULTI_ZONE_AC": "điều hòa tự động chia vùng",
    "LEATHER_SEATS": "ghế bọc da",
    "POWER_DRIVER_SEAT": "ghế lái chỉnh điện",
    "VENTILATED_SEATS": "ghế thông gió và sưởi",
    "HEAD_UP_DISPLAY": "màn hình hiển thị trên kính lái",
    "SMARTPHONE_MIRRORING": "kết nối Apple CarPlay và Android Auto",
    "POWER_TAILGATE": "cốp sau chỉnh điện",
}

#: Nhãn cho câu hỏi lượt 2 — nguồn nhãn CHÍNH của câu hỏi (Sếp 2026-08-21: đảo
#: ưu tiên so với trước, xem `candidate_tuning._first_name`). DẪN XUẤT từ
#: `FEATURE_DISPLAY_LABELS` chứ không chép tay lần nữa: hai bản chép tay của cùng
#: một nhãn là hai bản sẽ lệch nhau.
FEATURE_LABELS: Final[Mapping[str, str]] = {
    code: FEATURE_DISPLAY_LABELS[code] for code in sorted(ALL_ASKABLE) if code in FEATURE_DISPLAY_LABELS
}


def askable_for(vehicle_type: VehicleType, bucket: PurposeBucket) -> frozenset[str]:
    """Allowlist cho (loại xe × mục đích); không khớp bucket thì trả toàn bộ mã
    CỦA ĐÚNG LOẠI XE ĐÓ (an toàn) — không lấy mã của nhánh xe kia."""
    return ASKABLE_FEATURES.get((vehicle_type, bucket), _ALL_ASKABLE_BY_VEHICLE_TYPE.get(vehicle_type, ALL_ASKABLE))
