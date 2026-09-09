"""Domain Need Tag Registry for Agent module (mục 7.0 / A1-4b).

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.
Định nghĩa tập closed set của NeedTag kèm mô tả tiếng Việt chi tiết dùng cho vector matching (2b).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class NeedTag(StrEnum):
    """Closed set of Need Tags for VinFast Sales Advisor (A1-4b)."""

    URBAN_TRAFFIC = "URBAN_TRAFFIC"
    FAMILY_TRIP = "FAMILY_TRIP"
    LONG_RANGE = "LONG_RANGE"
    DELIVERY_LOAD = "DELIVERY_LOAD"
    ECO_SAVING = "ECO_SAVING"
    PREMIUM_COMFORT = "PREMIUM_COMFORT"


@dataclass(frozen=True, slots=True)
class NeedTagDefinition:
    """Chi tiết một nhãn nhu cầu trong tập đóng."""

    tag: NeedTag
    name_vi: str
    description_vi: str
    default_feature_codes: tuple[str, ...]


NEED_TAG_REGISTRY: dict[NeedTag, NeedTagDefinition] = {
    NeedTag.URBAN_TRAFFIC: NeedTagDefinition(
        tag=NeedTag.URBAN_TRAFFIC,
        name_vi="Đi lại nội thành",
        description_vi=(
            "hay đi trong phố di chuyển hàng ngày trong thành phố đường đông đúc nhỏ hẹp dễ xoay xở tiết kiệm năng lượng. "
            "Hay đi trong phố, đi lại nội thành cần xe nhỏ gọn dễ đỗ, bán kính quay đầu gọn và dùng ít điện."
        ),
        default_feature_codes=("COMPACT_SIZE",),
    ),
    NeedTag.FAMILY_TRIP: NeedTagDefinition(
        tag=NeedTag.FAMILY_TRIP,
        name_vi="Du lịch gia đình",
        description_vi=(
            "Nhu cầu chở gia đình đi chơi, du lịch hoặc dã ngoại; ưu tiên đủ chỗ ngồi, ra vào các hàng ghế thuận tiện, "
            "khoang hành lý linh hoạt và trang bị giúp trẻ em, người lớn tuổi sử dụng xe an toàn, thoải mái."
        ),
        default_feature_codes=("7_SEATER", "PANORAMIC_ROOF"),
    ),
    NeedTag.LONG_RANGE: NeedTagDefinition(
        tag=NeedTag.LONG_RANGE,
        name_vi="Đi tỉnh đường dài",
        description_vi=(
            "Nhu cầu thường xuyên đi tỉnh, về quê hoặc chạy đường trường; ưu tiên quãng đường di chuyển dài giữa hai lần sạc, "
            "khả năng sạc nhanh và kế hoạch bổ sung năng lượng thuận tiện trên hành trình."
        ),
        default_feature_codes=("FAST_CHARGING",),
    ),
    NeedTag.DELIVERY_LOAD: NeedTagDefinition(
        tag=NeedTag.DELIVERY_LOAD,
        name_vi="Giao hàng chở nặng",
        description_vi=(
            "Nhu cầu giao hàng, vận chuyển đồ đạc hoặc chạy dịch vụ nhiều chuyến; ưu tiên tải trọng phù hợp, chỗ đặt hàng chắc chắn, "
            "pin dễ bổ sung năng lượng và khả năng vận hành ổn định khi sử dụng liên tục."
        ),
        # HIGH_PAYLOAD bị bỏ (0 cờ YES) — thay bằng BATTERY_SWAPPABLE: xe máy
        # giao hàng chạy liên tục sống nhờ đổi pin nhanh tại trạm.
        default_feature_codes=("BATTERY_SWAPPABLE",),
    ),
    NeedTag.ECO_SAVING: NeedTagDefinition(
        tag=NeedTag.ECO_SAVING,
        name_vi="Tiết kiệm chi phí",
        description_vi=(
            "Nhu cầu giảm chi phí đi lại hằng tháng; quan tâm mức tiêu thụ điện, khả năng sạc tại nhà, chi phí bảo dưỡng, "
            "độ bền pin và các lựa chọn giúp kiểm soát chi phí vận hành trong thời gian sử dụng."
        ),
        # ECO_MODE bị bỏ (0 cờ YES) — thay bằng BATTERY_REMOVABLE: pin tháo rời
        # mang vào nhà sạc giá rẻ, đúng nguồn tiết kiệm chi phí vận hành.
        default_feature_codes=("BATTERY_REMOVABLE",),
    ),
    NeedTag.PREMIUM_COMFORT: NeedTagDefinition(
        tag=NeedTag.PREMIUM_COMFORT,
        name_vi="Sang trọng tiện nghi",
        description_vi=(
            "Nhu cầu ưu tiên tiện nghi và trải nghiệm khoang xe; quan tâm chất liệu ghế, điều hòa, cửa sổ trời, hỗ trợ lái, "
            "kết nối điện thoại và các trang bị giúp hành trình thoải mái, gọn gàng, dễ sử dụng."
        ),
        default_feature_codes=("PANORAMIC_ROOF", "ADAS_SUITE"),
    ),
}


def get_need_tag_definition(tag_str: str) -> NeedTagDefinition | None:
    """Lấy định nghĩa need_tag từ tập đóng. Trả về None nếu nằm ngoài tập đóng."""
    try:
        need_enum = NeedTag(tag_str.upper())
        return NEED_TAG_REGISTRY.get(need_enum)
    except ValueError:
        return None


#: Lời khách viết TỰ DO → nhãn tập đóng, cho ba nhãn trước đây không có mẫu nào.
#:
#: `slot_extraction_prompts` dặn LLM ghi `habit_need_tags` "giữ nguyên lời
#: khách", nên mọi giá trị tới `scoring._need_tag_reasons` đều là tiếng Việt tự
#: do. Ba nhãn `DELIVERY_LOAD` / `ECO_SAVING` / `PREMIUM_COMFORT` không có mẫu
#: nào ở đây cho tới 2026-08-25 ⇒ "hay chở hàng nặng" rơi về chuỗi rác
#: `HAY_CH_H_NG_N_NG` và **không góp một điểm nào**. Im lặng, không log, không
#: lỗi — đúng bẫy `luong-tu-van-da-sua.md` mục 3.4, chỉ khác chỗ phát sinh.
#:
#: Mẫu phải khớp CỤM, không khớp từ lẻ. `chở` một mình không đủ: "chở gia đình"
#: là `FAMILY_TRIP`, không phải chở hàng. Cùng lý do `sang` phải đi với `trọng` —
#: "đi sang bên kia" không nói gì về xe sang.
_FREE_TEXT_NEED_TAGS: Final[tuple[tuple[str, str], ...]] = (
    (
        "DELIVERY_LOAD",
        r"\b(?:cho hang|cho do|cho nang|hang nang|giao hang|"
        r"cong kenh|tai trong|chay hang|van chuyen)\b",
    ),
    (
        "ECO_SAVING",
        r"\b(?:tiet kiem|an dien|it ton|re tien)\b|\bchi phi\b.{0,20}\bre\b|\bre\b.{0,15}\bchi phi\b",
    ),
    (
        # "thoai mai"/"em ai" là cách khách mô tả tiện nghi bằng lời thường —
        # xem chú thích ở `canonical_need_tag` về câu mở lời thật trên prod.
        "PREMIUM_COMFORT",
        r"\b(?:sang trong|cao cap|tien nghi|thoai mai|em ai|cua so troi|"
        r"kinh toan canh|noc kinh|ghe da|noi that da)\b",
    ),
)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d")).strip()


#: `canonical_need_tag` trả `LONG_DISTANCE` cho `LONG_RANGE` (catalog dùng tên
#: sau, `feature_introduction` dùng tên trước). Bí danh giữ cho `need_tag_display`
#: nhận cả hai, không dựng bản đọc thứ hai của cùng một nhãn.
_ENUM_ALIASES: Final[dict[str, NeedTag]] = {"LONG_DISTANCE": NeedTag.LONG_RANGE}


#: Tên tiếng Việt của nhãn → chính nhãn đó, khớp TOÀN CHUỖI.
#:
#: `slot_extraction` lưu `name_vi` chứ không lưu mã, vì giá trị slot còn đi thẳng
#: vào prompt tổng hợp (`nodes/synthesize._customer_wording`) — mã thô ở đó mời
#: LLM chép lại rồi `RAW_STRUCTURED_PATTERN` loại cả pitch (bẫy 3.9). Bảng này là
#: đường về: không có nó thì `name_vi` chỉ quy đúng nhờ MAY MẮN trùng regex bên
#: dưới, và một lần sửa chữ trong `NEED_TAG_REGISTRY` là im lặng mất điểm.
#:
#: Khớp toàn chuỗi nên nó KHÔNG cướp được câu nào của các nhánh sau.
_NAME_VI_TO_TAG: Final[dict[str, str]] = {
    _normalize(definition.name_vi): definition.tag.value for definition in NEED_TAG_REGISTRY.values()
}


def need_tag_display(value: str) -> str:
    """Nhãn tập đóng → tên tiếng Việt; mọi thứ khác GIỮ NGUYÊN lời khách.

    Cố ý chỉ đổi giá trị khớp ĐÚNG một thành viên `NeedTag`. Chữ tự do — của
    phiên cũ trong `conversation_slots`, hay do `_explicit_habit_need_tags` ghi
    bằng regex tất định — phải sống nguyên vẹn: quy nó về một nhãn gần đúng là
    đặt vào miệng khách một nhu cầu họ chưa nêu.
    """

    stripped = " ".join(value.split())
    definition = get_need_tag_definition(stripped) if stripped else None
    if definition is None:
        alias = _ENUM_ALIASES.get(stripped.upper())
        definition = NEED_TAG_REGISTRY[alias] if alias is not None else None
    return definition.name_vi if definition is not None else stripped


def canonical_need_tag(value: str) -> str:
    """Map stored enums and natural customer wording to one comparison key."""

    enum_style = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    if enum_style in {"LONG_RANGE", "LONG_DISTANCE"}:
        return "LONG_DISTANCE"
    if enum_style in {"URBAN_TRAFFIC", "FAMILY_TRIP", "DELIVERY_LOAD", "ECO_SAVING", "PREMIUM_COMFORT"}:
        return enum_style
    normalized = _normalize(value)
    named = _NAME_VI_TO_TAG.get(normalized)
    if named is not None:
        return "LONG_DISTANCE" if named == NeedTag.LONG_RANGE.value else named
    if normalized in {"long range", "long distance"} or re.search(
        r"\b(?:di xa|di tinh|duong dai|duong truong|ve que)\b", normalized
    ):
        return "LONG_DISTANCE"
    if normalized == "urban traffic" or re.search(r"\b(?:noi thanh|noi do|do thi|trong pho|quanh nha)\b", normalized):
        return "URBAN_TRAFFIC"
    # "rong rai" đứng cùng nhóm gia đình: khách mô tả khoang xe rộng là đang nói
    # về chỗ ngồi cho cả nhà, đúng thứ `FAMILY_TRIP` ưu tiên ("đủ chỗ ngồi, ra
    # vào các hàng ghế thuận tiện").
    #
    # Đọc từ `pending_feature_mentions` prod 2026-08-26 — câu mở lời thật:
    #
    #   "Tôi cần một chiếc SUV cho gia đình… Yêu cầu xe rộng rãi, thoải mái,
    #    tone màu trắng, bền bỉ"
    #
    # Bốn cụm đó lưu nguyên văn rồi không quy được về đâu: không mã tính năng
    # nào (bảng cụm chữ có 27 mã, không mã nào tả "rộng rãi"), và ở đây thì rơi
    # xuống nhánh cuối thành chuỗi rác `R_NG_R_I` — không khớp tag nào trong 8
    # tag thật, cộng 0 điểm, im lặng.
    if normalized == "family trip" or re.search(r"\b(?:gia dinh|ca nha|du lich|rong rai)\b", normalized):
        return "FAMILY_TRIP"
    # Ba nhãn mới xét SAU cùng: ba nhánh trên đã chạy thật từ lâu, mẫu mới không
    # được phép cướp một câu nào của chúng.
    for tag, pattern in _FREE_TEXT_NEED_TAGS:
        if re.search(pattern, normalized):
            return tag
    return enum_style


#: Khoá quy chuẩn của SÁU nhãn nhu cầu thật — chính là tập `canonical_need_tag`
#: có thể trả về một cách CÓ NGHĨA. Nhánh cuối của hàm đó trả `enum_style`, tức
#: chuỗi rác viết hoa của bất kỳ lời nào không quy được, nên nơi nào cần biết
#: "câu này có mô tả nhu cầu đi lại không" đều phải đối chiếu với tập này chứ
#: không được tin vào việc hàm trả về khác rỗng.
#:
#: `LONG_DISTANCE` chứ không phải `LONG_RANGE`: `canonical_need_tag` cố ý quy
#: `NeedTag.LONG_RANGE` về khoá cũ này.
USAGE_NEED_TAG_KEYS: Final[frozenset[str]] = frozenset(
    {
        "URBAN_TRAFFIC",
        "FAMILY_TRIP",
        "LONG_DISTANCE",
        "DELIVERY_LOAD",
        "ECO_SAVING",
        "PREMIUM_COMFORT",
    }
)


#: Bốn nhãn tả CHUYẾN ĐI: khách đi đâu, chở gì, chở ai.
#:
#: `ECO_SAVING` và `PREMIUM_COMFORT` cố ý ĐỨNG NGOÀI dù chúng cũng là nhãn thật:
#: "tiết kiệm" và "sang trọng tiện nghi" nói về CHIẾC XE và về tiền, không nói
#: khách dùng xe để làm gì. Lấy chúng làm mục đích thì câu "anh muốn xe tiết
#: kiệm" biến thành "mục đích: tiết kiệm" — một câu khách chưa nói.
_TRIP_NEED_TAG_KEYS: Final[frozenset[str]] = frozenset(
    {"URBAN_TRAFFIC", "FAMILY_TRIP", "LONG_DISTANCE", "DELIVERY_LOAD"}
)


def describes_travel_habit(value: str) -> bool:
    """Lời này có mô tả CHUYẾN ĐI không, hay chỉ là một sở thích về xe.

    "Đi lại nội thành" có; "nhỏ gọn" (mã tính năng `COMPACT_SIZE`) không —
    tính năng nói xe trông thế nào, không nói khách dùng xe để làm gì.
    """

    return canonical_need_tag(value) in _TRIP_NEED_TAG_KEYS
