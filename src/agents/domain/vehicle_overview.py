"""Domain contracts and intent classifier for structured vehicle overviews."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.agents.contracts import VehicleFacts
from src.agents.domain.text_normalization import contains_keyword
from src.agents.domain.values import VehicleType


class VehicleAttribute(StrEnum):
    """The catalog attribute requested by a customer message."""

    OVERVIEW = "OVERVIEW"
    PRICE = "PRICE"
    SEAT_COUNT = "SEAT_COUNT"
    DIMENSIONS = "DIMENSIONS"
    POWERTRAIN = "POWERTRAIN"
    RANGE = "RANGE"
    SUSPENSION = "SUSPENSION"
    AIR_CONDITIONING = "AIR_CONDITIONING"
    INFOTAINMENT = "INFOTAINMENT"
    SAFETY = "SAFETY"
    AIRBAG = "AIRBAG"
    SUNROOF = "SUNROOF"
    COLOR = "COLOR"
    INTERIOR_COLOR = "INTERIOR_COLOR"
    SPECS = "SPECS"
    WARRANTY = "WARRANTY"
    UNKNOWN = "UNKNOWN"


OVERVIEW_KEYWORDS: Final[tuple[str, ...]] = (
    "tư vấn",
    "chi tiết",
    "đầy đủ",
    "tất cả thông tin",
    "toàn bộ thông tin",
    "thông tin về xe",
    "thông tin xe",
)


#: Từ khoá nhận diện từng field, XẾP THEO THỨ TỰ ƯU TIÊN — khớp đầu tiên thắng.
#:
#: Thứ tự là toàn bộ phần khó ở đây. "giá" và "bao nhiêu" từng nằm chung một
#: nhóm PRICE đặt trước mọi thứ, nên "vf5 chở được bao nhiêu người", "vf5 công
#: suất bao nhiêu" và "vf5 màn hình bao nhiêu inch" đều bị đọc thành hỏi giá.
#: Vì vậy field CỤ THỂ đứng trước, và PRICE chỉ nhận các cụm thật sự nói về tiền.
#:
#: [GIẢ ĐỊNH] Danh sách từ khoá gom từ cách hỏi thường gặp, chưa phủ hết tiếng
#: Việt đời thường. Bổ sung theo log hội thoại thật; nhầm về `UNKNOWN` chỉ khiến
#: khách nhận bảng đầy đủ (thừa), còn nhầm sang field khác là trả lời sai.
FIELD_KEYWORDS: Final[tuple[tuple[VehicleAttribute, tuple[str, ...]], ...]] = (
    (VehicleAttribute.AIRBAG, ("túi khí",)),
    (VehicleAttribute.SUNROOF, ("cửa sổ trời", "cửa sổ nóc", "nóc kính")),
    (
        VehicleAttribute.SEAT_COUNT,
        (
            "mấy chỗ",
            "bao nhiêu chỗ",
            "số chỗ",
            "chở được bao nhiêu người",
            "chở bao nhiêu người",
            "chở mấy người",
            "bao nhiêu người",
            "mấy người",
            "mấy ghế",
        ),
    ),
    (VehicleAttribute.WARRANTY, ("bảo hành", "bảo dưỡng", "chính sách pin", "thời hạn pin")),
    (VehicleAttribute.INTERIOR_COLOR, ("màu nội thất", "nội thất màu", "màu ghế")),
    (VehicleAttribute.COLOR, ("màu",)),
    (
        VehicleAttribute.RANGE,
        (
            "đi được bao xa",
            "đi được bao nhiêu km",
            "quãng đường",
            "tầm hoạt động",
            "một lần sạc",
            "1 lần sạc",
            "sạc đầy",
            "bao nhiêu km",
        ),
    ),
    (VehicleAttribute.AIR_CONDITIONING, ("điều hòa", "điều hoà", "máy lạnh")),
    (VehicleAttribute.SUSPENSION, ("hệ thống treo", "giảm xóc", "phuộc")),
    (
        VehicleAttribute.INFOTAINMENT,
        (
            "màn hình",
            "giải trí",
            "loa",
            "usb",
            "bluetooth",
            "kết nối",
            "cổng sạc",
            "ứng dụng",
            " app",
        ),
    ),
    (
        VehicleAttribute.DIMENSIONS,
        ("kích thước", "chiều dài", "chiều rộng", "chiều cao", "cơ sở", "dài rộng cao"),
    ),
    (
        VehicleAttribute.POWERTRAIN,
        (
            "công suất",
            "mô-men",
            "mô men",
            "momen",
            "động cơ",
            "dung lượng pin",
            "pin",
            "tốc độ tối đa",
            "tăng tốc",
            "dẫn động",
        ),
    ),
    (
        VehicleAttribute.SAFETY,
        (
            "an toàn",
            "abs",
            "esc",
            "esp",
            "hsa",
            "điểm mù",
            "camera lùi",
            "chống trộm",
            "adas",
            "phanh",
        ),
    ),
    (VehicleAttribute.OVERVIEW, OVERVIEW_KEYWORDS),
    (VehicleAttribute.PRICE, ("giá", "bao nhiêu tiền", "bao nhiêu đồng", "giá bao nhiêu")),
    (VehicleAttribute.SPECS, ("thông số",)),
)


def classify_query_attribute(message: str) -> VehicleAttribute:
    """Phân loại khách đang hỏi FIELD nào của xe.

    Trước đây chỉ "giá" có nhánh riêng; mọi câu hỏi field khác rơi về `UNKNOWN`
    và nhận nguyên bảng thông số. Khách hỏi "vf5 có mấy chỗ ngồi" được trả cả
    động cơ, pin, màn hình, an toàn lẫn giá — câu trả lời đúng nằm lẫn trong đó
    nhưng khách phải tự đi tìm.

    Khớp BỎ DẤU (`contains_keyword`): bảng từ khoá viết có dấu, còn khách gõ
    nhanh thì không. So trực tiếp thì "vf5 gia bao nhieu" rơi về `UNKNOWN` và
    khách hỏi giá lại nhận nguyên bảng thông số — đúng thứ hàm này sinh ra để
    sửa, chỉ khác ở chỗ nguyên nhân là dấu chứ không phải thiếu nhánh.

    `UNKNOWN` KHÔNG phải lỗi: nó là "khách nêu tên xe mà không nhắm field nào",
    và câu trả lời đúng cho nó vẫn là bảng đầy đủ.
    """

    for attribute, keywords in FIELD_KEYWORDS:
        if any(contains_keyword(message, keyword) for keyword in keywords):
            return attribute
    return VehicleAttribute.UNKNOWN


class PriceVariant(BaseModel):
    """A verified list price for one vehicle variant and region."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vehicle_id: UUID
    variant_name: str
    amount_vnd: Decimal
    price_type: str
    region_code: str


class DimensionsInfo(BaseModel):
    """Optional physical dimensions read from the catalog."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    length_mm: int | None = None
    width_mm: int | None = None
    height_mm: int | None = None
    wheelbase_mm: int | None = None
    ground_clearance_mm: int | None = None


class EngineVariantSpecs(BaseModel):
    """Powertrain specifications for one vehicle variant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_name: str
    motor_power_kw: Decimal | None = None
    torque_nm: Decimal | None = None
    drivetrain: str | None = None
    # Thông số vận hành từ bảng `cars` (danh mục đã xác minh). Trước đây pin /
    # tầm chạy / tốc độ chỉ đến từ tài liệu RAG, nên mẫu chưa có tài liệu (VF 5,
    # prod 2026-08-29) chỉ in được công suất + mô-men.
    battery_capacity_kwh: Decimal | None = None
    range_km: Decimal | None = None
    range_cycle: str | None = None
    max_speed_kmh: Decimal | None = None
    fast_charge_time_minutes: int | None = None
    fast_charge_from_percent: int | None = None
    fast_charge_to_percent: int | None = None


class EngineSpecs(BaseModel):
    """Powertrain specifications grouped by vehicle variant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variants: list[EngineVariantSpecs] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """A renderable RAG evidence excerpt with its stable source identifier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)

    @field_validator("content", "evidence_id")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        """Reject evidence fields that have no non-whitespace value."""

        if not value.strip():
            raise ValueError("evidence fields must not be blank")
        return value


class ColorInfo(BaseModel):
    """Deterministic catalog colour names and sourced colour evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    names: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)


class VehicleOverview(BaseModel):
    """All optional data groups rendered for one resolved vehicle family."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vehicle_name: str
    price_variants: list[PriceVariant] = Field(default_factory=list)
    dimensions: DimensionsInfo | None = None
    engine_specs: EngineSpecs | None = None
    highlights: list[EvidenceItem] = Field(default_factory=list)
    features: list[EvidenceItem] = Field(default_factory=list)
    safety_systems: list[EvidenceItem] = Field(default_factory=list)
    colors: ColorInfo | None = None


@dataclass(frozen=True, slots=True)
class ResolvedVehicleFamily:
    """The active variants belonging to one catalog vehicle family."""

    vehicle_name: str
    vehicle_type: VehicleType
    vehicle_ids: tuple[UUID, ...]
    variant_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmbiguousVehicleResolution:
    """Marker returned when one normalized mention matches multiple families."""

    vehicle_name: str


@dataclass(frozen=True, slots=True)
class VehicleOverviewResult:
    """Structured overview output and lookup facts for downstream quote handling."""

    overview: VehicleOverview | None = None
    answer: str | None = None
    lookup_facts: tuple[VehicleFacts, ...] = ()
    unmatched: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()
