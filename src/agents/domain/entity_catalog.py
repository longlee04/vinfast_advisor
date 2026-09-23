"""[Lớp 2] Danh mục thực thể TĨNH để fuzzy match — gom nguồn, không tự đặt ra.

Ba danh mục theo đúng thứ tự ưu tiên nghiệp vụ:

1. **Xe** — tên mẫu xe VinFast. Nguồn sự thật vẫn là bảng `vehicles`; module này
   giữ một seed tĩnh để tầng nhận diện chạy được cả khi chưa nối DB, và nhận
   thêm tên thật qua tham số `vehicle_names` khi đã nối.
2. **Thuộc tính** — sinh TỪ `FIELD_KEYWORDS` của `domain/vehicle_overview.py`,
   không chép tay lại. Chép tay là dựng nguồn sự thật thứ hai: thêm một từ khoá
   cho `VehicleAttribute.COLOR` ở đó mà quên chép sang đây thì hai lớp hiểu khác
   nhau về cùng một câu, và không có test nào bắt được.
3. **Từ khoá intent** — bảng curated riêng cho việc NHẬN DIỆN, cố ý tách khỏi
   `domain/intent_reconciliation.py`.

   [GIẢ ĐỊNH] Tách hai bảng là có chủ đích, không phải trùng lặp bỏ sót:
   `intent_reconciliation` là bộ HOÀ GIẢI nhãn cuối cùng, chạy trên câu đã sạch
   và vẫn là nguồn sự thật DUY NHẤT của `state["intents"]`. Bảng ở đây chỉ dùng
   để đo "câu này trông giống ý định nào" trên câu CÒN NHIỄU, phục vụ tính
   confidence. Gộp hai bảng sẽ buộc regex hoà giải phải chịu được cả input rác.

Sinh alias cho số đếm tiếng Việt ("vf năm" → "VF 5") là phần đắt giá nhất ở đây:
nó bắt được đúng ca lỗi gốc mà không cần một lần gọi LLM nào, nên Lớp 2 vẫn
nhận ra xe kể cả khi Lớp 1 bị bỏ qua hoặc trả về kết quả không dùng được.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.text_normalization import (
    VIETNAMESE_DIGIT_WORDS,
    normalize,
    squash,
)
from src.agents.domain.values import Intent
from src.agents.domain.vehicle_overview import FIELD_KEYWORDS


class EntityCategory(StrEnum):
    """Loại thực thể mà Lớp 2 trích được từ câu của khách."""

    VEHICLE = "VEHICLE"
    ATTRIBUTE = "ATTRIBUTE"
    INTENT_KEYWORD = "INTENT_KEYWORD"


#: Seed tên mẫu xe. [GIẢ ĐỊNH] Đây là ảnh chụp `vehicles.model_name` tại thời
#: điểm viết (`data-p150/catalog/vehicles.csv`), KHÔNG phải nguồn sự thật: khi
#: `vehicle_names` được truyền vào, danh sách thật từ catalog được cộng thêm.
#: Giữ seed vì tầng nhận diện phải chạy được ở test và ở môi trường chưa có DB.
SEED_CAR_MODELS: Final[tuple[str, ...]] = (
    "VF 2",
    "VF 3",
    "VF 5",
    "VF 6",
    "VF 7",
    "VF 8",
    "VF 9",
    "VF Wild",
    # `VF e34` KHÔNG còn trong catalog hiện hành. Vẫn nhận diện được là CỐ Ý:
    # khách hỏi một xe đã ngừng bán thì câu trả lời đúng là "mẫu này không còn
    # trong danh mục hiện hành" (nhánh `unmatched_mentions` của A4-1 đã làm sẵn),
    # chứ không phải im lặng coi như khách chưa nêu tên xe nào.
    "VF e34",
)

#: Danh sách xe máy điện lấy nguyên từ `prompts/scope_prompts.py` — nơi cùng
#: một danh mục đã được liệt kê cho bộ phân loại phạm vi (A6-2). Chép từ đó thay
#: vì gõ lại theo trí nhớ để hai chỗ không nói hai danh mục khác nhau.
SEED_MOTORBIKE_MODELS: Final[tuple[str, ...]] = (
    "Amio",
    "DrgnFly",
    "Evo",
    "Evo 200",
    "Evo Grand",
    "Evo Lite",
    "Evo Max",
    "Feliz",
    "Flazz",
    "Impes",
    "Kinet",
    "Klara",
    "Kyo",
    "Ludo",
    "Motio",
    "Tempest",
    "Theon",
    "Vento",
    "Vero X",
    "Viper",
    "ZGoo",
)

#: Từ khoá nhận diện ý định, dùng cho câu CÒN NHIỄU. Xem docstring module về lý
#: do bảng này tách khỏi `intent_reconciliation`.
INTENT_KEYWORDS: Final[Mapping[Intent, tuple[str, ...]]] = {
    Intent.CATALOG_BROWSE: (
        "xe máy điện",
        "ô tô điện",
        "xe điện",
        "danh sách xe",
        "có những xe gì",
        "có xe nào",
        "cửa hàng có",
        "đang bán",
        "tất cả xe",
        "các mẫu xe",
    ),
    Intent.CATALOG_LOOKUP: (
        "thông tin xe",
        "thông số",
        "giá bao nhiêu",
        "bao nhiêu tiền",
        "giá lăn bánh",
        "chi tiết",
    ),
    # "so sánh" ĐÃ CHUYỂN sang `COMPARE_VEHICLES` bên dưới. Giữ nó ở
    # `CATALOG_LOOKUP` là dạy Lớp 3 rằng câu so sánh cũng chỉ là một lượt tra
    # cứu, và đó đúng là hành vi cũ: khách hỏi "so sánh VF3 và VF5" nhận về hai
    # bảng thông số nối đuôi nhau thay vì một bảng đặt cạnh nhau.
    Intent.COMPARE_VEHICLES: (
        "so sánh",
        "so với",
        "khác gì",
        "khác nhau",
        "khác biệt",
        "đối chiếu",
        "nên chọn",
        "tốt hơn",
        "hay hơn",
        "xe nào",
    ),
    # [FIND_NEARBY_LOCATION] Chỉ DANH TỪ ĐỊA ĐIỂM, không có chữ "sạc" trần. Cùng
    # ranh giới mà `domain/nearby_location._STATION_NOUN` đang giữ, và vì cùng
    # một lý do: "sạc" một mình còn là tiêu chí tư vấn (`HOME_CHARGING`), nên đưa
    # nó vào đây sẽ dạy Lớp 3 chấm mọi câu hỏi về sạc tại nhà thành câu hỏi đường.
    #
    # "showroom"/"đại lý" nằm ở đây chứ KHÔNG ở `CATALOG_BROWSE`: hai intent đó
    # trả hai thứ khác hẳn nhau — một danh sách ĐỊA CHỈ có nút chỉ đường, và một
    # danh sách XE có giá. "cửa hàng có xe nào" vẫn về `CATALOG_BROWSE` vì nó
    # thiếu dấu hiệu định vị mà `is_nearby_location_request` đòi.
    Intent.FIND_NEARBY_LOCATION: (
        # Trạm sạc
        "trạm sạc",
        "trụ sạc",
        "điểm sạc",
        "chỗ sạc",
        "trạm sạc ô tô",
        "trạm sạc xe máy điện",
        "trạm sạc gần nhất",
        "sạc ở đâu",
        # Đổi pin
        "trạm đổi pin",
        "tủ đổi pin",
        "trụ đổi pin",
        "chỗ đổi pin",
        "đổi pin",
        # Showroom
        "showroom",
        "showroom ô tô",
        "showroom xe máy điện",
        "showroom gần nhất",
        "đại lý",
        "đại lý ô tô",
        "đại lý xe máy điện",
        "chi nhánh",
        # Xưởng dịch vụ
        "gara",
        "gara ô tô",
        "xưởng dịch vụ",
        "trung tâm bảo hành",
        "bảo dưỡng",
        # Chung
        "chỉ đường",
        "địa điểm gần nhất",
        "vị trí",
    ),
    Intent.ADVISORY: (
        "tư vấn",
        "gợi ý",
        "phù hợp",
        "nên mua",
        "cần xe",
        "muốn mua",
        "ngân sách",
    ),
}

#: Cách gọi thân mật / cách gõ tắt ngoài mã model chính thức → tên như catalog ghi.
#:
#: [KHÁC BIỆT] Bảng `vehicles` KHÔNG có cột alias/nickname (xem
#: `src/products/infrastructure/models.VehicleRow`), nên "dùng field alias của
#: catalog để match" không thực hiện được như đặc tả mô tả. Bảng tĩnh này là chỗ
#: thay thế gần nhất, và nó nằm ở ĐÂY — cùng chỗ với mọi alias khác của Lớp 2 —
#: chứ không nằm trong nhánh so sánh, để cả tra cứu lẫn so sánh cùng nhận ra một
#: cách gọi. Khi catalog có cột alias thật, thay bảng này bằng tham số truyền vào
#: `default_catalog`, không phải sửa logic khớp.
#: [GIẢ ĐỊNH] Bảng cố ý NGẮN. Mỗi dòng thêm vào là một cách để một câu vô hại
#: bị đọc thành tên xe, và alias sai nguy hiểm hơn alias thiếu — thiếu thì Lớp 1
#: hoặc câu hỏi lại cứu được, sai thì khách nhận bảng thông số của một xe khác.
#: Chỉ nhận cách gọi mà bộ sinh alias tự động KHÔNG phủ: dạng số đếm tiếng Việt
#: ("vf năm") đã do `VIETNAMESE_DIGIT_WORDS` sinh sẵn nên không lặp lại ở đây,
#: và tên phiên bản ("VF 5 Plus") thuộc về `resolve_vehicle_names`, không phải
#: một biệt danh.
VEHICLE_NICKNAMES: Final[Mapping[str, tuple[str, ...]]] = {
    "VF 3": ("vép 3", "vinfast 3"),
    "VF 5": ("vép 5", "vinfast 5"),
    "VF 8": ("vép 8", "vinfast 8"),
    "VF 9": ("vép 9", "vinfast 9"),
    "Evo 200": ("evo hai trăm",),
    "Feliz": ("phê lít",),
}


@dataclass(frozen=True, slots=True)
class EntityAlias:
    """Một cách viết của một thực thể, đã ở dạng chuẩn hoá để so khớp."""

    #: Dạng đã chuẩn hoá (không dấu, thường). Đây là thứ đưa vào `rapidfuzz`.
    alias: str
    #: Giá trị chuẩn trả về khi khớp — tên xe như catalog ghi, hoặc giá trị enum.
    canonical: str
    category: EntityCategory
    #: Số token của alias. Lưu sẵn để Lớp 2 biết cần cắt cửa sổ mấy từ, khỏi
    #: phải tách chuỗi lại cho từng alias ở mỗi lượt.
    token_count: int

    @classmethod
    def build(cls, raw: str, canonical: str, category: EntityCategory) -> EntityAlias | None:
        """Dựng alias từ chuỗi thô; chuỗi rỗng sau chuẩn hoá → `None`."""

        normalized = normalize(raw)
        if not normalized:
            return None
        return cls(
            alias=normalized,
            canonical=canonical,
            category=category,
            token_count=len(normalized.split()),
        )


@dataclass(frozen=True, slots=True)
class EntityCatalog:
    """Toàn bộ alias của cả ba danh mục, gom một chỗ để Lớp 2 quét một lần."""

    aliases: tuple[EntityAlias, ...] = ()

    def canonical_names(self, category: EntityCategory) -> tuple[str, ...]:
        """Giá trị chuẩn đã khử trùng, giữ thứ tự — dùng để gợi ý cho khách."""

        seen: dict[str, None] = {}
        for item in self.aliases:
            if item.category is category:
                seen.setdefault(item.canonical, None)
        return tuple(seen)


def _vehicle_alias_forms(display_name: str) -> tuple[str, ...]:
    """Mọi cách khách có thể gõ một tên xe.

    "VF 5" → "vf 5" (như catalog), "vf5" (viết liền — cách gõ phổ biến nhất),
    "vf nam" (đọc số thành chữ — cách gõ mà không bộ khớp chính xác nào bắt được).

    Sinh chiều ngược của `VIETNAMESE_DIGIT_WORDS` chứ không viết tay từng dòng:
    thêm một mẫu xe mới vào catalog thì alias số-thành-chữ có ngay, không phải
    nhớ cập nhật một bảng thứ hai.
    """

    normalized = normalize(display_name)
    if not normalized:
        return ()
    forms = {normalized, squash(display_name)}
    tokens = normalized.split()
    for word, digit in VIETNAMESE_DIGIT_WORDS.items():
        if digit in tokens:
            forms.add(" ".join(word if token == digit else token for token in tokens))
    return tuple(forms)


def build_vehicle_aliases(display_names: Iterable[str]) -> tuple[EntityAlias, ...]:
    """Alias cho danh mục xe. `canonical` giữ NGUYÊN VĂN tên đã truyền vào.

    Không tự viết hoa hay chuẩn hoá lại `canonical`: giá trị này được chuyển
    xuống `IntentRoutingService.lookup_facts` để tra catalog, nên nó phải khớp
    đúng cách catalog ghi, không phải cách module này nghĩ là đẹp.
    """

    built: list[EntityAlias] = []
    for name in display_names:
        forms = (*_vehicle_alias_forms(name), *VEHICLE_NICKNAMES.get(name, ()))
        for form in forms:
            alias = EntityAlias.build(form, name, EntityCategory.VEHICLE)
            if alias is not None:
                built.append(alias)
    return tuple(built)


def build_attribute_aliases() -> tuple[EntityAlias, ...]:
    """Alias thuộc tính, sinh từ `FIELD_KEYWORDS` — nguồn sự thật duy nhất.

    `UNKNOWN` không có từ khoá nào trong bảng gốc nên tự nhiên vắng mặt: nó là
    "khách không nhắm thuộc tính nào", tức trạng thái KHÔNG khớp, không phải một
    thực thể có thể khớp được.
    """

    built: list[EntityAlias] = []
    for attribute, keywords in FIELD_KEYWORDS:
        for keyword in keywords:
            alias = EntityAlias.build(keyword, attribute.value, EntityCategory.ATTRIBUTE)
            if alias is not None:
                built.append(alias)
    return tuple(built)


def build_intent_keyword_aliases() -> tuple[EntityAlias, ...]:
    """Alias từ khoá intent, từ bảng `INTENT_KEYWORDS` của chính module này."""

    built: list[EntityAlias] = []
    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            alias = EntityAlias.build(keyword, intent.value, EntityCategory.INTENT_KEYWORD)
            if alias is not None:
                built.append(alias)
    return tuple(built)


def default_catalog(vehicle_names: Sequence[str] | None = None) -> EntityCatalog:
    """Danh mục dùng khi chạy thật.

    `vehicle_names=None` → chỉ seed tĩnh. Truyền danh sách thật từ catalog thì
    seed vẫn được giữ: một mẫu xe vừa bị gỡ khỏi `vehicles` vẫn nên NHẬN DIỆN
    được để trả lời "mẫu này không còn trong danh mục", thay vì rơi về "em chưa
    hiểu ý anh/chị".
    """

    names: list[str] = [*SEED_CAR_MODELS, *SEED_MOTORBIKE_MODELS]
    if vehicle_names:
        seen = {normalize(name) for name in names}
        names.extend(name for name in vehicle_names if normalize(name) not in seen)
    return EntityCatalog(
        aliases=(
            *build_vehicle_aliases(names),
            *build_attribute_aliases(),
            *build_intent_keyword_aliases(),
        )
    )


#: Mẫu xe gợi ý khi không hiểu được câu của khách (nhánh confidence THẤP).
#: [GIẢ ĐỊNH] "Phổ biến" ở đây là phỏng đoán theo dải giá phổ thông, KHÔNG có
#: cột doanh số nào trong catalog để xếp hạng. Khi có dữ liệu bán hàng thật thì
#: thay danh sách này bằng truy vấn, không phải sửa logic.
POPULAR_MODEL_SUGGESTIONS: Final[tuple[str, ...]] = ("VF 3", "VF 5", "VF 6", "VF 7")


__all__ = [
    "INTENT_KEYWORDS",
    "VEHICLE_NICKNAMES",
    "POPULAR_MODEL_SUGGESTIONS",
    "SEED_CAR_MODELS",
    "SEED_MOTORBIKE_MODELS",
    "EntityAlias",
    "EntityCatalog",
    "EntityCategory",
    "build_attribute_aliases",
    "build_intent_keyword_aliases",
    "build_vehicle_aliases",
    "default_catalog",
]
