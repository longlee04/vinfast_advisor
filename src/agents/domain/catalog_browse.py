"""[A4-7] Liệt kê danh mục xe theo LOẠI — nhận diện loại và dựng câu trả lời.

Bug gốc: "các xe máy điện có trong cửa hàng" bị coi là tên MỘT MẪU XE và đem đi
tra `vehicles.model_name`, không khớp dòng nào, khách nhận "Em chưa tìm thấy 'xe
máy điện' trong danh mục VinFast hiện hành." Câu đó không sai kỹ thuật — nó trả
lời đúng câu hỏi "có mẫu xe nào TÊN LÀ 'xe máy điện' không", chỉ là khách không
hỏi câu đó.

Nhánh này KHÔNG lọc theo nhu cầu và KHÔNG cần slot nào: khách đã nói đủ ("loại
gì") ngay ở lượt đầu, nên hỏi ngược lại ngân sách/số người trước khi cho xem
danh mục là bắt họ trả giá cho một thứ họ chưa yêu cầu.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK. Toàn bộ câu
chữ ở đây là template deterministic — cùng lý do với `domain/catalog_reply.py`,
đó là vì sao nhánh này được A7-4 cho đi thẳng tới khách, không cần người duyệt.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID

from src.agents.domain.reply_format import BULLET, bold, italic
from src.agents.domain.values import VehicleType

# ── Nhận diện LOẠI xe khách nêu ───────────────────────────────────────────────
#
# Khớp theo RANH GIỚI TỪ, không phải chuỗi con — cùng lý do và cùng khuôn với
# `pricing_intent.detect_province`. Bản không dấu "o to" nằm trong "cho toi", nên
# tìm chuỗi con sẽ biến "gợi ý cho toi cac xe may dien" thành một câu hỏi về ô tô.
#
# Bảng này cũng là bảng bộ trích slot `vehicle_type` dùng
# (`domain/slot_salvage.salvaged_vehicle_type`). Một bảng duy nhất là có chủ đích:
# hai bảng thì "xe điện 2 bánh" nhận ra được ở nhánh xem danh mục mà không nhận
# ra được khi khách trả lời câu hỏi loại xe, và không ai phát hiện ra sự lệch đó.
_MOTORBIKE_KEYWORDS: Final[tuple[str, ...]] = (
    "motorbike",
    "motorcycle",
    "xe máy điện",
    "xe may dien",
    "xe máy",
    "xe may",
    "xe ga điện",
    "xe ga dien",
    "xe tay ga điện",
    "xe tay ga dien",
    "xe tay ga",
    "mô tô điện",
    "mo to dien",
    "moto điện",
    "moto dien",
    "xe điện 2 bánh",
    "xe dien 2 banh",
    "xe điện hai bánh",
    "xe dien hai banh",
    "xe 2 bánh",
    "xe 2 banh",
    "xe hai bánh",
    "xe hai banh",
)
_CAR_KEYWORDS: Final[tuple[str, ...]] = (
    "car",
    "ô tô",
    "ôtô",
    "o to",
    "oto",
    "xe hơi",
    "xe hoi",
    "xe con",
    "xe 4 bánh",
    "xe 4 banh",
    "xe bốn bánh",
    "xe bon banh",
    "xe điện 4 bánh",
    "xe dien 4 banh",
    "xe điện bốn bánh",
    "xe dien bon banh",
)

#: Tên hiển thị của từng loại trong câu trả lời.
_TYPE_LABEL: Final[dict[VehicleType, str]] = {
    VehicleType.ELECTRIC_MOTORBIKE: "Xe máy điện",
    VehicleType.CAR: "Ô tô điện",
}

#: Thứ tự trình bày khi khách hỏi nhiều loại cùng lúc. Cố định để hai lần hỏi
#: giống nhau không nhận về hai thứ tự khác nhau.
BROWSE_TYPE_ORDER: Final[tuple[VehicleType, ...]] = (
    VehicleType.ELECTRIC_MOTORBIKE,
    VehicleType.CAR,
)

#: Số khoảng giá chia trong một loại, và số xe tối thiểu để việc chia có nghĩa.
#: Dưới ngưỡng này thì liệt kê phẳng — chia 4 mẫu xe thành ba nhóm không giúp
#: khách đọc nhanh hơn, chỉ thêm ba dòng tiêu đề.
_BAND_COUNT: Final[int] = 3
_MIN_ENTRIES_TO_BAND: Final[int] = 6

#: Câu MỜI ở cuối danh mục: một lời dẫn IN ĐẬM rồi ba mục đánh số.
#:
#: Ba lần đổi, và lần nào cũng do một thứ khác nhau gây ra — ghi lại để không
#: quay vòng (Sếp 2026-08-25):
#:
#: 1. Bản đầu hỏi ngân sách + mục đích + "yêu cầu đặc biệt", nằm dưới một danh
#:    sách bảy dòng xe VÀ trên năm thẻ xe. Sếp báo "quá nhiều thông tin".
#: 2. Rút còn MỘT câu hỏi ngân sách. Nhưng thứ làm màn hình dài không phải câu
#:    mời — mà là mấy tấm thẻ xe trùng lặp, nay đã bỏ. Câu mời một dòng nằm lọt
#:    thỏm giữa danh sách và dòng lưu ý, khách đọc lướt là không thấy.
#: 3. Bản này: lời dẫn in đậm nói rõ ĐỔI LẠI ĐƯỢC GÌ ("để em tư vấn mẫu xe phù
#:    hợp nhất"), rồi ba mục đánh số cho ba thứ cây slot cần sớm nhất.
#:
#: MỤC ĐÍCH có kèm ví dụ ("đi làm, chở gia đình đi xa, chạy dịch vụ, giao hàng").
#: Hỏi trống "mục đích của anh/chị là gì" thì khách trả lời tự do đủ kiểu; nêu
#: sẵn bốn hướng thì câu trả lời rơi đúng vào `PurposeBucket` — khoá chọn
#: allowlist tính năng ở lượt sau.
#:
#: Đánh SỐ chứ không dùng bullet `*`: bullet ở đây sẽ lẫn với các dòng xe phía
#: trên, cả với mắt khách lẫn với `_model_lines` trong test.
#: HAI mục, không phải ba (Sếp 2026-08-26). "Số người sử dụng" đã rời bước thu
#: thập cùng lúc với `slot_tree.OPENING_GROUP`: nó chỉ CỘNG ĐIỂM xếp hạng, không
#: lọc bỏ ứng viên nào, nên hỏi nó là tốn một mục cho thứ không đổi được kết quả.
#:
#: Nhánh này phải đi CÙNG NHỊP với `prompts/combined_intake` — hai chỗ hỏi cùng
#: một bộ thông tin thì phải hỏi cùng những mục. Chạy thật trên prod 2026-08-26
#: cho thấy chúng đã lệch: khách bấm nút loại xe rơi vào nhánh danh mục và vẫn
#: nhận đủ ba mục cũ, trong khi khách đi đường thường chỉ nhận hai.
_INVITATION_LEAD: Final[str] = (
    "**Để em tư vấn mẫu xe phù hợp nhất với Quý khách, Quý khách cho em xin hai thông tin ạ:**\n\n"
    "1. **Ngân sách**: Quý khách dự tính khoảng bao nhiêu cho chiếc xe này ạ?\n"
)

#: Gợi ý mục đích, TÁCH THEO LOẠI XE — vì mục đích chỉ có tác dụng ở đúng một nhánh.
#:
#: Đo trên chính `domain/scoring._purpose_reasons` (Sếp 2026-08-25):
#:
#:     mục đích      ô tô                      xe máy điện
#:     gia đình      khoang hành lý  ✅        — (không có cột cốp)
#:     đi làm        tầm hoạt động   ✅        tầm hoạt động     ✅
#:     dịch vụ       tiêu thụ điện   ✅        tiêu thụ điện     ✅
#:     giao hàng     — (không tác dụng)        pin tháo rời      ✅
#:     đi xa/về quê  tầm hoạt động   ✅        tầm hoạt động     ✅
#:
#: "Giao hàng" ở nhánh ô tô đòi `battery_removable`/`battery_swappable` — hai cột
#: CHỈ bảng `motorbikes` mới có, ô tô luôn rỗng. Gợi ý nó cho khách mua ô tô là
#: mời họ chọn một đáp án không đổi được gì. Ngược lại "chở gia đình" ở nhánh xe
#: máy đòi cột cốp, cũng chết y hệt.
#:
#: `feature_askable.ASKABLE_FEATURES` xác nhận cùng một điều: không có mục nào
#: cho `(CAR, DELIVERY)`.
#: Mỗi gợi ý phải MỒI bằng một con số ki-lô-mét, y như `prompts/combined_intake`.
#:
#: Đó là cách duy nhất còn lại để lấy quãng đường/ngày mà không hỏi thành một mục
#: riêng: khách bắt chước dạng của ví dụ. Bỏ số đi thì khách cũng trả lời không
#: số, và bảng chi phí lại chạy trên mốc mặc định.
#: Ví dụ phải giữ ĐỦ hai thứ, mất cái nào cũng hỏng một nửa:
#:
#: - một con số ki-lô-mét — cách duy nhất còn lại để lấy quãng đường/ngày mà
#:   không hỏi thành mục riêng, vì khách bắt chước dạng của ví dụ;
#: - các mục đích ĂN ĐIỂM của ĐÚNG nhánh đó — "chở gia đình" chỉ có tác dụng ở ô
#:   tô (đòi cột cốp), "giao hàng" chỉ có tác dụng ở xe máy (đòi pin tháo rời).
#:   Gợi sai nhánh là mời khách chọn một đáp án không đổi được gì.
_PURPOSE_HINT: Final[dict[VehicleType, str]] = {
    VehicleType.CAR: (
        "Quý khách cần xe cho việc gì và thường đi lại ra sao ạ? "
        "(ví dụ: đi làm khoảng 30 km mỗi ngày, cuối tuần chở gia đình đi chơi, "
        "hay về quê đường dài, chạy dịch vụ)"
    ),
    VehicleType.ELECTRIC_MOTORBIKE: (
        "Quý khách cần xe cho việc gì và thường đi lại ra sao ạ? "
        "(ví dụ: đi làm khoảng 15 km mỗi ngày, hay chạy giao hàng, chạy dịch vụ, "
        "đi lại cá nhân)"
    ),
}

#: Gợi ý dùng khi câu hỏi phủ CẢ HAI loại xe: hợp của hai nhánh, bỏ những mục
#: đích chỉ đúng một bên.
_PURPOSE_HINT_BOTH: Final[str] = (
    "Quý khách cần xe cho việc gì và thường đi lại ra sao ạ? "
    "(ví dụ: đi làm khoảng 30 km mỗi ngày, chở gia đình đi chơi, về quê đường dài, "
    "chạy dịch vụ hay giao hàng)"
)


def closing_invitation(vehicle_types: Sequence[VehicleType]) -> str:
    """Câu mời cuối danh mục, gợi ý mục đích theo đúng loại xe đang liệt kê."""

    if len(vehicle_types) == 1:
        hint = _PURPOSE_HINT.get(vehicle_types[0], _PURPOSE_HINT_BOTH)
    else:
        hint = _PURPOSE_HINT_BOTH
    # Mục 2, không phải mục 3 — "Số người sử dụng" đã rời danh sách.
    question, example = hint.split(" (", maxsplit=1)
    example_text = f"({example}"
    return f"{_INVITATION_LEAD}2. **Nhu cầu & thói quen đi lại**: {question}\n{italic(example_text)}"


#: Giữ tên cũ cho test và chỗ gọi ngoài: mặc định là bản phủ cả hai loại.
CLOSING_INVITATION: Final[str] = closing_invitation(())


@dataclass(frozen=True, slots=True)
class BrowseEntry:
    """Một BIẾN THỂ xe trong danh mục, ở mức chi tiết vừa đủ để giới thiệu.

    Một dòng xe có nhiều biến thể (`VF 6 Eco`, `VF 6 Plus`) nên là NHIỀU entry.
    Renderer gộp chúng lại theo `model_name` — xem `render_browse_answer`.

    Vài thông số được mang theo, nhưng CHỈ những thông số đủ để viết một câu giới
    thiệu dòng xe (kiểu thân xe, số chỗ, tầm chạy, tốc độ, hạng giấy phép). Đây
    không phải chỗ trả bảng thông số: khách chốt được mẫu quan tâm thì nhánh
    `CATALOG_LOOKUP` sẵn sàng trả bảng đầy đủ của đúng xe đó.

    Mọi field mới đều optional và mặc định rỗng: thiếu thông số thì câu giới thiệu
    bỏ đúng vế đó, không bịa một giá trị thay thế và không làm vỡ danh sách.
    """

    vehicle_id: UUID
    display_name: str
    vehicle_type: VehicleType
    starting_price_vnd: Decimal | None = None
    #: Tên DÒNG xe, không kèm biến thể ("VF 6", "Evo Grand"). Rỗng → renderer lùi
    #: về `display_name`, tức hành vi y như trước khi có việc gộp theo dòng.
    model_name: str = ""
    variant_name: str | None = None
    #: `vehicles.slug` — dùng dựng liên kết "Xem thêm" tới trang xe trên chính
    #: web này (`/vehicles/<slug>`), không phải trang ngoài: khách bấm xong vẫn
    #: quay lại được cuộc tư vấn đang dở. Rỗng → dòng đó không có liên kết, danh
    #: sách vẫn nguyên vẹn.
    slug: str = ""
    #: `cars.body_type` — "SUV", "Hatchback". Đọc thẳng từ catalog, KHÔNG dịch và
    #: KHÔNG suy ra phân khúc: `vehicles` không có cột segment nào, nên mọi nhãn
    #: kiểu "phân khúc B" là phán đoán catalog không chứng minh được.
    body_type: str | None = None
    seat_count: int | None = None
    range_km: Decimal | None = None
    max_speed_kmh: Decimal | None = None
    #: `motorbikes.license_requirement` — "A1" hoặc "NONE". Thông tin phân biệt
    #: mạnh nhất giữa các dòng xe máy điện với người mua ở Việt Nam.
    license_requirement: str | None = None

    @property
    def model_key(self) -> str:
        """Khoá gộp theo dòng xe."""

        return self.model_name or self.display_name


def requested_vehicle_types(
    user_message: str, *, default_vehicle_type: VehicleType | None = None
) -> tuple[VehicleType, ...]:
    """Loại xe khách vừa nhắc tới, theo `BROWSE_TYPE_ORDER`.

    Không nêu loại nào ("có xe nào không", "cửa hàng có những xe gì") → trả CẢ
    HAI loại. Đây là chiều đúng: câu đó hỏi toàn bộ cửa hàng, và đoán bừa một
    loại là giấu mất nửa danh mục mà khách không biết mình đang bị giấu.

    "Xe điện" trần cũng rơi vào ca này — nó đúng cho cả ô tô lẫn xe máy của
    VinFast, nên không có cách nào chọn một loại mà không phải đoán.
    """

    normalized = " ".join((user_message or "").split()).casefold()
    found = {
        vehicle_type
        for vehicle_type, keywords in (
            (VehicleType.ELECTRIC_MOTORBIKE, _MOTORBIKE_KEYWORDS),
            (VehicleType.CAR, _CAR_KEYWORDS),
        )
        if any(_mentions(normalized, keyword) for keyword in keywords)
    }
    if not found and default_vehicle_type is not None:
        return (default_vehicle_type,)
    if not found:
        return BROWSE_TYPE_ORDER
    return tuple(item for item in BROWSE_TYPE_ORDER if item in found)


def _mentions(normalized: str, keyword: str) -> bool:
    """Từ khoá có xuất hiện như một TỪ trong câu không."""

    pattern = rf"(?<![a-zà-ỹ0-9]){re.escape(keyword)}(?![a-zà-ỹ0-9])"
    return re.search(pattern, normalized) is not None


# ── Dựng câu trả lời ──────────────────────────────────────────────────────────


def render_browse_answer(
    groups: Mapping[VehicleType, Sequence[BrowseEntry]],
) -> str | None:
    """Danh mục theo DÒNG XE, hoặc `None` khi không loại nào có xe.

    Một dòng một mẫu, kèm một câu giới thiệu ngắn, KHÔNG kèm giá. Ba lý do, và
    không lý do nào là "cho gọn":

    - Đây là lượt khách vừa nói mình muốn loại xe nào, chưa nói mình có bao nhiêu
      tiền. Trả về một bảng giá lúc này là bắt họ tự lọc theo con số duy nhất họ
      chưa được hỏi, trong khi việc còn lại của lượt là ĐI HỎI ngân sách.
    - Giá theo BIẾN THỂ, còn giới thiệu theo DÒNG. Liệt kê `VF 6 Eco` và
      `VF 6 Plus` thành hai dòng giá khiến khách đếm ra 11 lựa chọn ô tô, trong
      khi VinFast chỉ có 7 dòng — con số sai ngay ở câu mở đầu cuộc tư vấn.
    - Một câu tả kiểu thân xe/số chỗ giúp khách tự loại được nửa danh mục; một
      con số giá thì không, cho tới khi họ biết mình cần xe mấy chỗ.

    Giá vẫn được dùng — để SẮP THỨ TỰ (rẻ trước), vì đó là thứ tự đọc tự nhiên
    của một danh mục. Xe chưa công bố giá xuống cuối chứ không bị loại: nó vẫn
    đang bán, và đây là danh sách "có những dòng nào", không phải bảng giá.

    Mỗi loại là một KHỐI RIÊNG khi khách hỏi hai loại trong cùng một câu: trộn 27
    dòng xe máy với 7 dòng ô tô vào một danh sách phẳng thì không so sánh được thứ
    gì, và thứ tự giá sẽ xếp một chiếc Theon cạnh một chiếc VF 2.
    """

    ordered = [
        (vehicle_type, _by_model(groups.get(vehicle_type) or ()))
        for vehicle_type in BROWSE_TYPE_ORDER
        if groups.get(vehicle_type)
    ]
    ordered = [(vehicle_type, models) for vehicle_type, models in ordered if models]
    if not ordered:
        return None

    blocks = [_headline(ordered)]
    # Chỉ đánh số và gắn tiêu đề loại khi có TỪ HAI loại: một mình "Ô tô điện —
    # 7 dòng" ngay dưới câu mở đã nói đúng thông tin đó là lặp lại thừa.
    multiple = len(ordered) > 1
    for index, (vehicle_type, models) in enumerate(ordered, start=1):
        lines = [_model_line(name, variants) for name, variants in models]
        if multiple:
            label = f"{_TYPE_LABEL[vehicle_type]} — {len(models)} dòng đang bán"
            lines = [f"{index}. {bold(label)}:", *lines]
        blocks.append("\n".join(lines))
    blocks.append(closing_invitation([vehicle_type for vehicle_type, _models in ordered]))
    return "\n\n".join(blocks)


def _by_model(
    entries: Sequence[BrowseEntry],
) -> list[tuple[str, list[BrowseEntry]]]:
    """Gộp biến thể về dòng xe, sắp rẻ trước và xe chưa có giá xuống cuối.

    Thứ tự trong một dòng xe giữ nguyên thứ tự đầu vào (adapter đã sắp theo tên
    biến thể ngay trong SQL), nên hai lần hỏi cùng một câu nhận về cùng một câu
    trả lời.
    """

    grouped: dict[str, list[BrowseEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.model_key, []).append(entry)

    def sort_key(item: tuple[str, list[BrowseEntry]]) -> tuple[int, Decimal, str]:
        name, variants = item
        prices = [variant.starting_price_vnd for variant in variants if variant.starting_price_vnd is not None]
        # Chưa công bố giá → nhóm 1, xuống cuối. Không thay bằng 0: một chiếc VF
        # Wild giá chưa công bố mà đứng đầu danh sách đọc như xe rẻ nhất.
        if not prices:
            return (1, Decimal(0), name)
        return (0, min(prices), name)

    return sorted(grouped.items(), key=sort_key)


def _model_line(model_name: str, variants: Sequence[BrowseEntry]) -> str:
    """Một bullet: TÊN DÒNG XE in đậm + câu giới thiệu, hoặc chỉ tên khi thiếu thông số.

    Tên dòng xe là "tên trường" của bullet này — nó là thứ khách quét mắt tìm
    trong một danh sách 27 dòng xe máy, nên nó in đậm như mọi tên trường khác.
    """

    description = _model_description(variants)
    body = f"{bold(model_name)}: {description}" if description else bold(model_name)
    link = _detail_link(model_name)
    if link:
        body = f"{body} {link}"
    return f"{BULLET} {body}"


#: Đường dẫn trang xe trên web này, theo TÊN DÒNG XE.
#:
#: KHÔNG suy từ `vehicles.slug` của catalog (`vinfast-vf-8-all-new`): route
#: `/vehicles/[slug]` không đọc catalog, nó đọc `frontend/src/mocks/vehicle-menu`
#: và chỉ nhận đúng những id trong đó. Bản đầu dùng slug catalog nên MỌI liên kết
#: "Xem thêm" đều trỏ vào trang 404 — Em phát hiện lúc kiểm sau khi deploy
#: (2026-08-25), không phải lúc viết.
#:
#: Bảng tra TAY chứ không sinh tự động (`"VF 8"` → `"vf-8"` thì đúng, nhưng
#: `"VF Wild"` → `"vf-wild"` lại là 404): chỉ dòng xe nào THẬT SỰ có trang mới
#: được liệt kê. Thiếu trang thì dòng đó không có liên kết — vẫn đọc được bình
#: thường, không dẫn khách tới ngõ cụt.
#:
#: Thêm một dòng xe mới vào catalog mà quên bảng này thì chỉ mất liên kết, không
#: vỡ gì — `test_every_linked_model_has_a_real_page` canh chiều ngược lại.
_MODEL_PAGE_SLUG: Final[dict[str, str]] = {
    "VF 2": "vf-2",
    "VF 3": "vf-3",
    "VF 5": "vf-5",
    "VF 6": "vf-6",
    "VF 7": "vf-7",
    "VF 8": "vf-8",
    "VF 9": "vf-9",
}


def page_slug_for_name(display_name: str) -> str:
    """Slug trang xe từ TÊN HIỂN THỊ ("VinFast VF 8 Plus" → "vf-8"), hoặc rỗng.

    Cùng bảng `_MODEL_PAGE_SLUG` với link "Xem thêm" — một nguồn cho mọi đường
    dẫn `/vehicles/<slug>` mà lõi phát ra (`navigate.kind="vehicle"`). Tên hiển
    thị mang cả hãng lẫn biến thể, nên bỏ tiền tố hãng rồi khớp DÒNG dài nhất
    đứng đầu ("VF 8 Plus" khớp "VF 8", không khớp "VF 8 P…" nào khác); "VF 3"
    không được khớp "VF 3x" nhờ điều kiện ký tự kế tiếp là hết chuỗi/khoảng trắng.
    """

    short = display_name.strip()
    for prefix in ("VinFast ", "Vinfast ", "vinfast "):
        if short.startswith(prefix):
            short = short[len(prefix) :].strip()
    folded = short.casefold()
    for model in sorted(_MODEL_PAGE_SLUG, key=len, reverse=True):
        key = model.casefold()
        if folded == key or folded.startswith(key + " "):
            return _MODEL_PAGE_SLUG[model]
    return ""


#: Trang xe máy điện `/motorbikes/<id>` — id lấy đúng từ
#: `frontend/src/mocks/motorbike-menu.ts` (generateStaticParams đọc bảng đó).
#: Cùng luật bảng ô tô: chỉ liệt kê dòng THẬT SỰ có trang; khớp dòng dài nhất
#: trước ("Evo Grand Lite" không được rơi vào "Evo").
_MOTORBIKE_PAGE_SLUG: Final[dict[str, str]] = {
    "Vero X": "vero-x",
    "Viper": "viper",
    "Kinet": "kinet",
    "Feliz II": "feliz-ii",
    "Feliz": "feliz-2025",
    "Kyo": "kyo",
    "Evo Grand Lite": "evo-grand-lite",
    "Evo Grand": "evo-grand",
    "Evo Lite Neo": "evo-lite-neo",
    "Evo Lite": "evo-lite",
    "Evo": "evo",
    "Flazz Max": "flazz-max",
    "Flazz": "flazz",
    "ZGoo": "zgoo",
    "Amio S2": "amio-s2",
    "Amio S": "amio-s",
    "Amio": "amio",
    "DrgnFly": "vf-drgnfly-ebike",
}


def page_path_for_name(display_name: str) -> str:
    """Đường dẫn trang thật cho MỌI loại xe, hoặc rỗng nếu chưa có trang.

    Ô tô → `/vehicles/<slug>` (bảng `_MODEL_PAGE_SLUG`); xe máy →
    `/motorbikes/<id>` (bảng `_MOTORBIKE_PAGE_SLUG`). Một cửa duy nhất cho
    `navigate.path` — client không phải đoán prefix theo loại xe nữa.
    """

    car = page_slug_for_name(display_name)
    if car:
        return f"/vehicles/{car}"
    short = display_name.strip()
    for prefix in ("VinFast ", "Vinfast ", "vinfast "):
        if short.startswith(prefix):
            short = short[len(prefix) :].strip()
    folded = short.casefold()
    for model in sorted(_MOTORBIKE_PAGE_SLUG, key=len, reverse=True):
        key = model.casefold()
        if folded == key or folded.startswith(key + " "):
            return f"/motorbikes/{_MOTORBIKE_PAGE_SLUG[model]}"
    return ""


def _detail_link(model_name: str) -> str:
    """Liên kết "Xem thêm" tới trang của dòng xe trên chính web này.

    Trỏ vào `/vehicles/<slug>` chứ không ra trang ngoài: khách bấm xong vẫn quay
    lại được cuộc tư vấn đang dở, và khung xem trước khi rê chuột
    (`components/common/preview-link`) chỉ nhúng được trang cùng nguồn.
    """

    slug = _MODEL_PAGE_SLUG.get(model_name.strip())
    return f"[Xem thêm](/vehicles/{slug})" if slug else ""


def _model_description(variants: Sequence[BrowseEntry]) -> str:
    """Câu giới thiệu một dòng xe, ghép từ thông số CÓ THẬT trong catalog.

    Không có cột `description` hay `segment` nào trong `vehicles`, nên câu này
    được ghép từ những cột có thật (`cars.body_type`, `seat_count`, `range_km`;
    `motorbikes.range_max_km`, `max_speed_kmh`, `license_requirement`). Đó là lý
    do nó KHÔNG bao giờ nói "phân khúc B" hay "phù hợp cho gia đình nhỏ": cả hai
    đều là phán đoán marketing mà catalog không chứng minh được, và một câu giới
    thiệu bịa ra thì tệ hơn một câu chỉ có tên xe.

    Thiếu hết thông số → trả chuỗi rỗng, dòng đó chỉ còn tên xe. Vẫn tốt hơn một
    câu tả rỗng nghĩa.
    """

    if not variants:
        return ""
    parts = _car_parts(variants) if variants[0].vehicle_type is VehicleType.CAR else _motorbike_parts(variants)
    versions = _versions_part(variants)
    if versions:
        parts = [*parts, versions]
    if not parts:
        return ""
    return _sentence(parts)


def _car_parts(variants: Sequence[BrowseEntry]) -> list[str]:
    """Kiểu thân xe + số chỗ + tầm chạy — đọc thẳng từ `cars`."""

    parts: list[str] = []
    shape = _first(variant.body_type for variant in variants)
    seats = _first(variant.seat_count for variant in variants)
    if shape and seats:
        parts.append(f"{shape} {seats} chỗ")
    elif shape:
        parts.append(str(shape))
    elif seats:
        parts.append(f"xe {seats} chỗ")
    span = _range_span(variant.range_km for variant in variants)
    if span:
        parts.append(f"tầm chạy {span} km mỗi lần sạc")
    return parts


def _motorbike_parts(variants: Sequence[BrowseEntry]) -> list[str]:
    """Tầm chạy + tốc độ + hạng giấy phép — đọc thẳng từ `motorbikes`.

    Hạng giấy phép đứng CUỐI nhưng là vế đáng giá nhất với người mua ở Việt Nam:
    "không cần giấy phép lái xe" loại hoặc chọn cả một nhóm xe ngay lập tức.
    """

    parts: list[str] = []
    span = _range_span(variant.range_km for variant in variants)
    if span:
        parts.append(f"tầm chạy tới {span} km")
    speed = _range_span(variant.max_speed_kmh for variant in variants)
    if speed:
        parts.append(f"tốc độ tối đa {speed} km/h")
    license_note = _license_note(variants)
    if license_note:
        parts.append(license_note)
    return parts


def _license_note(variants: Sequence[BrowseEntry]) -> str | None:
    """Chỉ nói khi CẢ dòng xe cùng một hạng — biến thể lệch nhau thì im lặng."""

    codes = {variant.license_requirement for variant in variants if variant.license_requirement}
    if len(codes) != 1:
        return None
    code = next(iter(codes))
    if code.upper() == "NONE":
        return "không cần giấy phép lái xe"
    return f"cần giấy phép lái xe hạng {code}"


def _versions_part(variants: Sequence[BrowseEntry]) -> str | None:
    """Liệt kê biến thể khi dòng xe có nhiều hơn một.

    Tên biến thể giữ NGUYÊN VĂN như catalog ghi. Không dịch "All New" thành "thế
    hệ mới": khách hỏi lại đúng cái tên vừa đọc thì tra cứu phải khớp, mà bản dịch
    thì không có trong `vehicles.variant_name`.
    """

    names = list(
        dict.fromkeys(
            variant.variant_name.strip()
            for variant in variants
            if variant.variant_name and variant.variant_name.strip()
        )
    )
    if len(names) < 2:
        return None
    return f"có {len(names)} phiên bản ({', '.join(names)})"


def _headline(
    ordered: Sequence[tuple[VehicleType, list[tuple[str, list[BrowseEntry]]]]],
) -> str:
    """Câu mở: chào, nói dải sản phẩm, rồi dẫn vào danh sách.

    Đếm đúng số DÒNG xe, không nói "nhiều mẫu" chung chung và cũng không đếm số
    biến thể — xem `render_browse_answer` về việc vì sao con số đó sai.
    """

    labels = [_TYPE_LABEL[vehicle_type].casefold() for vehicle_type, _ in ordered]
    counts = " và ".join(
        f"{len(models)} dòng {_TYPE_LABEL[vehicle_type].casefold()}" for vehicle_type, models in ordered
    )
    return (
        f"Dạ, VinFast hiện có dải sản phẩm {' và '.join(labels)} đa dạng, phục vụ "
        f"nhiều nhu cầu khác nhau. Dưới đây là {counts} đang bán ạ:"
    )


def _first(values: Iterable[object | None]) -> object | None:
    """Giá trị đầu tiên có mặt; dùng cho thông số giống nhau giữa các biến thể."""

    for value in values:
        if value is not None and value != "":
            return value
    return None


def _range_span(values: Iterable[Decimal | None]) -> str | None:
    """ "326" hoặc "310–315" — một con số khi các biến thể bằng nhau, hai khi không.

    Không lấy trung bình và không lấy riêng số lớn nhất: khách đọc "tầm chạy 562
    km" rồi mua đúng bản chạy 457 km là một câu sai có hậu quả.
    """

    numbers = sorted({Decimal(value) for value in values if value is not None})
    if not numbers:
        return None
    if len(numbers) == 1:
        return _plain_number(numbers[0])
    return f"{_plain_number(numbers[0])}–{_plain_number(numbers[-1])}"


def _plain_number(amount: Decimal) -> str:
    """`Decimal("210.00")` → "210"; giữ phần thập phân khi nó có nghĩa."""

    if amount == amount.to_integral_value():
        return str(int(amount))
    return f"{amount.normalize():f}".replace(".", ",")


def _sentence(parts: Sequence[str]) -> str:
    """Ghép các vế thành một câu, viết hoa chữ đầu và đóng bằng dấu chấm."""

    body = ", ".join(parts)
    return body[:1].upper() + body[1:] + "."


__all__ = [
    "BROWSE_TYPE_ORDER",
    "CLOSING_INVITATION",
    "closing_invitation",
    "BrowseEntry",
    "render_browse_answer",
    "requested_vehicle_types",
]
