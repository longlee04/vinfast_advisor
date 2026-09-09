"""Dựng câu trả lời thông tin xe theo format chuẩn của AI Sales Advisor.

Format cũ trả một dòng gộp mọi thứ ("VF 3: giá niêm yết từ …, số chỗ 4 chỗ, …"),
khó đọc và không có chỗ cho thông số chi tiết. Format này thay hẳn nó — bố cục
Markdown chung của mọi câu trả lời, khai ở `domain/reply_format`:

    <đoạn mở đầu 2-3 câu, không bullet>

    1. **Thông số kỹ thuật**:
    * **Kích thước**: <giá trị>
    * **Động cơ & Vận hành**: <giá trị>, <giá trị>

    2. **An toàn**:
    * **Trang bị an toàn**: <giá trị>

    3. **Giá bán**: từ <số> (đã bao gồm VAT).

    <đoạn mời + 2 câu kết cố định>

Ba luật cứng, và cả ba đều theo cùng một hướng — KHÔNG nói thứ catalog không
biết:

1. Nhóm nào không có dữ liệu thì BỎ HẲN dòng đó, không ghi "chưa có thông tin".
   Mục lớn mất hết trường con thì mất luôn cả tiêu đề, và số thứ tự chạy lại từ
   đầu trên các mục còn lại.
2. Không bịa số, không suy diễn từ số khác.
3. Không lộ `evidence_id`, không lặp một thông tin ở hai chỗ.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK. Toàn bộ câu
chữ ở đây là template deterministic — chính vì thế nhánh tra cứu này được A7-4
cho đi thẳng tới khách, không cần tư vấn viên duyệt.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from decimal import Decimal
from typing import Final

from src.agents.contracts import VehicleFacts
from src.agents.domain.reply_format import (
    ReplySection,
    bold,
    field_line,
    join_blocks,
    render_sections,
)
from src.agents.domain.values import VehicleType

#: Dòng cảnh báo cuối câu trả lời TRA CỨU. Rút còn một câu (Sếp 2026-08-26:
#: "quá rườm rà").
#:
#: Bản cũ mở bằng "Hy vọng thông tin trên hữu ích với Quý khách" rồi mới vào
#: phần cảnh báo — bốn dòng chữ cho một ý, và vế mở đầu không nói thêm gì. Vế
#: cảnh báo thì GIỮ: nó là ranh giới giữa "chatbot tham khảo" và "báo giá chính
#: thức", và bỏ nó là bỏ một tuyên bố có ràng buộc.
#:
#: KHÔNG dán vào câu HỎI. Nó chỉ thuộc về câu trả lời có số liệu — xem
#: `catalog_browse.render_browse_answer`.
CLOSING_NOTE: Final[str] = (
    "Thông tin trên để Quý khách tham khảo nhanh; số liệu chính thức xin liên hệ bộ phận chuyên trách của VinFast."
)

#: Tiêu đề mục thông số. Không còn mang dấu hai chấm: `render_sections` tự thêm
#: dấu và tự bọc in đậm, nên nhúng sẵn ở đây sẽ ra "**Thông số kỹ thuật:**:".
SPEC_HEADING: Final[str] = "Thông số kỹ thuật"

#: Câu mời ngắn đặt TRƯỚC disclaimer, đóng vai "đoạn kết" của format chuẩn.
#: Cố ý không nhận định "xe này hợp với ai": catalog không có dữ liệu nào chứng
#: minh một nhận định như thế, và bịa nó ra ngay dưới một bảng thông số đã xác
#: minh là chỗ khách dễ tin nhầm nhất.
SHEET_INVITATION: Final[str] = "Quý khách cho em biết thêm nhu cầu sử dụng để em tư vấn phiên bản phù hợp ạ."

#: Tiêu đề mục giá. Khai riêng vì `_specs_answer` phải LOẠI đúng mục này ra —
#: so bằng chuỗi viết tay ở hai chỗ thì đổi tiêu đề một chỗ là mục giá lặng lẽ
#: quay lại trong câu trả lời "cho xem thông số".
PRICE_HEADING: Final[str] = "Giá bán"

# [GIẢ ĐỊNH] `vehicle_prices` KHÔNG có cột nào nói giá đã gồm VAT hay chưa. Format
# lại bắt buộc phải ghi rõ, nên câu này là hằng số một chỗ duy nhất, theo thông lệ
# niêm yết của VinFast tại Việt Nam. Đây là câu DUY NHẤT trong file nói một điều
# catalog không chứng minh được — khi bảng giá có cột VAT thì đọc từ đó và xoá
# hằng số này đi.
VAT_NOTE: Final[str] = "đã bao gồm VAT"

# Nhóm hiển thị của bảng thông số, khai theo MÃ tính năng.
#
# [GIẢ ĐỊNH] Không suy ra từ `feature_definitions.category`: category gom theo
# mục đích nội bộ, không theo nhóm của bảng gửi khách — `SMART_FEATURE` chứa lẫn
# GPS/Bluetooth (đúng là giải trí & kết nối) với `ANTI_THEFT`, `BATTERY_SWAPPABLE`
# (không phải giải trí). Đổ nguyên category vào dòng "Màn hình & Giải trí" là dán
# nhãn sai cho khách đọc.
#
# Mã không nằm trong bảng nào dưới đây sẽ KHÔNG xuất hiện trong bảng thông số —
# thà thiếu một dòng còn hơn xếp nó vào nhóm sai. Thêm feature_code mới vào
# catalog thì bổ sung vào đây.
#: Ba nhóm dưới đây MỞ (không `_`) vì `domain/vehicle_details` dùng lại chúng.
#: Hai bản phân nhóm cho cùng một mã là hai chỗ để lệch, và chỗ lệch ấy chỉ lộ ra
#: khi khách thấy một tính năng an toàn nằm trong mục tiện nghi.
SAFETY_CODES: Final[tuple[str, ...]] = ("ADAS_SUITE", "ANTI_THEFT")
INFOTAINMENT_CODES: Final[tuple[str, ...]] = ("BLUETOOTH", "ESIM", "GPS", "MOBILE_APP")
COMFORT_CODES: Final[tuple[str, ...]] = ("PANORAMIC_ROOF",)
_SAFETY_CODES = SAFETY_CODES
_INFOTAINMENT_CODES = INFOTAINMENT_CODES
_COMFORT_CODES = COMFORT_CODES
# Thứ tự ưu tiên khi chọn ĐÚNG MỘT điểm nổi bật cho đoạn mở đầu.
_HIGHLIGHT_ORDER: Final[tuple[str, ...]] = (
    "ADAS_SUITE",
    "PANORAMIC_ROOF",
    "FAST_CHARGING",
    "HIGH_RANGE_BATTERY",
    "ESIM",
    "MOBILE_APP",
)

# Tên đầy đủ ngắn gọn cho các viết tắt an toàn. Chỉ dùng khi tên trong catalog
# CHÍNH LÀ viết tắt — không tự chú giải cho tên đã đầy đủ.
SAFETY_GLOSSARY: Final[dict[str, str]] = {
    "ADAS": "hỗ trợ lái nâng cao",
    "ABS": "chống bó cứng phanh",
    "EBD": "phân phối lực phanh điện tử",
    "BA": "hỗ trợ lực phanh khẩn cấp",
    "ESC": "cân bằng điện tử",
    "TCS": "kiểm soát lực kéo",
    "HSA": "hỗ trợ khởi hành ngang dốc",
    "ESS": "đèn báo phanh khẩn cấp",
    "TPMS": "cảm biến áp suất lốp",
}


def format_vnd(amount: Decimal) -> str:
    """Format an integral VND amount with Vietnamese thousands separators."""

    return f"{int(amount):,}".replace(",", ".") + " đồng"


def render_lookup_answer(
    facts: Sequence[VehicleFacts],
    unmatched: Sequence[str] = (),
    ambiguous: Sequence[str] = (),
) -> str | None:
    """Câu trả lời gửi khách, hoặc `None` khi không có thông tin nào đã xác minh.

    Một xe → bảng thông số đầy đủ theo format chuẩn. Nhiều xe → mỗi xe một dòng
    tóm tắt [GIẢ ĐỊNH]: format chuẩn là bảng thông số của MỘT xe, xếp ba bảng
    chồng lên nhau không trả lời được câu hỏi nào mà chỉ tạo một bức tường chữ.
    Khách hỏi rõ một xe thì nhận đúng bảng đầy đủ.
    """

    if len(facts) == 1:
        return _join_blocks([_vehicle_sheet(facts[0]), _unresolved_note(unmatched, ambiguous)])
    if facts:
        summary = "\n".join(field_line(item.display_name, _price_phrase(item)) for item in facts)
        return _join_blocks(
            [
                "Dạ, thông tin nhanh các mẫu xe Quý khách hỏi:",
                summary,
                "Quý khách cho biết cụ thể mẫu xe quan tâm để em gửi thông số chi tiết ạ.",
                _unresolved_note(unmatched, ambiguous),
            ]
        )
    note = _unresolved_note(unmatched, ambiguous)
    return note or None


def _vehicle_sheet(facts: VehicleFacts) -> str:
    """Bảng thông số đầy đủ của một xe, đúng thứ tự mục đã quy định.

    Mở đầu → các mục lớn (đánh số khi có ≥2) → đoạn mời → hai câu kết. Mỗi mục
    lớn gom các trường CÙNG NHÓM lại, và tên trường nào cũng in đậm — đây là
    thứ khách quét mắt tìm khi đọc một bảng thông số.
    """

    return _join_blocks(
        [
            _opening(facts),
            *render_sections(_sheet_sections(facts)),
            SHEET_INVITATION,
            CLOSING_NOTE,
        ]
    )


def _sheet_sections(facts: VehicleFacts) -> list[ReplySection]:
    """Các mục lớn của bảng thông số, theo đúng thứ tự khách quen đọc.

    Mục nào không có trường nào có dữ liệu thì `render_sections` bỏ hẳn — không
    in tiêu đề rỗng, và số thứ tự chạy lại từ đầu trên các mục còn lại.
    """

    return [
        ReplySection(SPEC_HEADING, tuple(_technical_fields(facts))),
        ReplySection("Nội thất & Tiện nghi", tuple(_comfort_fields(facts))),
        ReplySection("An toàn", tuple(_safety_fields(facts))),
        ReplySection("Ngoại thất", tuple(_exterior_fields(facts))),
        ReplySection(PRICE_HEADING, value=_price_value(facts)),
    ]


def _opening(facts: VehicleFacts) -> str:
    """Đoạn mở đầu 2-3 câu, không bullet.

    Chỉ nói ba thứ: phân khúc, điểm nổi bật thiết kế, một tiện ích nổi bật nhất —
    và bỏ vế nào không có dữ liệu thay vì viết câu rỗng.
    """

    sentences = [f"Dạ, {facts.display_name} là mẫu xe thuần điện của VinFast."]
    segment = _segment_phrase(facts)
    if segment is not None:
        sentences.append(segment)
    highlight = _highlight_phrase(facts)
    if highlight is not None:
        sentences.append(highlight)
    return " ".join(sentences)


def _segment_phrase(facts: VehicleFacts) -> str | None:
    """Phân khúc + điểm nổi bật thiết kế, dựng từ kiểu dáng và số chỗ."""

    body = _as_text(facts.specs.get("body_type"))
    seats = _as_text(facts.specs.get("seat_count"))
    if body is None and seats is None:
        return None
    parts = [part for part in (body, f"{seats} chỗ ngồi" if seats else None) if part]
    return f"Xe thuộc phân khúc {', '.join(parts)}."


def _highlight_phrase(facts: VehicleFacts) -> str | None:
    """Đúng MỘT tiện ích/công nghệ nổi bật, không liệt kê cả danh sách.

    Chọn theo thứ tự ưu tiên khai sẵn chứ không lấy phần tử đầu của một dict:
    thứ tự dict phụ thuộc thứ tự đọc từ database, nên "điểm nổi bật" sẽ đổi theo
    những thay đổi chẳng liên quan gì tới xe. Giữ nguyên chữ hoa/thường của tên
    trong catalog — hạ thường "Anti Theft" thành "anti theft" là làm hỏng tên riêng.
    """

    for code in _HIGHLIGHT_ORDER:
        name = facts.features.get(code)
        if name:
            return f"Xe được trang bị {name}."
    return None


def _technical_fields(facts: VehicleFacts) -> list[tuple[str, str]]:
    """Nhóm kỹ thuật: kích thước, động cơ & vận hành, hệ thống treo."""

    builders = (_dimensions_field, _powertrain_field, _suspension_field)
    return [pair for build in builders if (pair := build(facts)) is not None]


def _comfort_fields(facts: VehicleFacts) -> list[tuple[str, str]]:
    """Nhóm nội thất & tiện nghi: điều hoà, màn hình & giải trí, màu nội thất."""

    builders = (_air_conditioning_field, _infotainment_field, _interior_colour_field)
    return [pair for build in builders if (pair := build(facts)) is not None]


def _safety_fields(facts: VehicleFacts) -> list[tuple[str, str]]:
    """Nhóm an toàn, tách khỏi nhóm kỹ thuật vì khách đọc nó như một mục riêng."""

    pair = _safety_field(facts)
    return [pair] if pair is not None else []


def _exterior_fields(facts: VehicleFacts) -> list[tuple[str, str]]:
    """Nhóm ngoại thất: hiện chỉ có bảng màu ngoại thất."""

    pair = _exterior_colour_field(facts)
    return [pair] if pair is not None else []


def _dimensions_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Kích thước: DxRxC, chiều dài cơ sở.

    Catalog chưa có cột nào cho các số này (`cars`/`motorbikes` không lưu kích
    thước tổng thể), nên nhóm này luôn bị bỏ qua cho tới khi schema bổ sung.
    """

    values = _present(
        ("Dài x Rộng x Cao", _as_text(facts.specs.get("dimensions_lwh_mm"))),
        ("chiều dài cơ sở", _with_unit(facts.specs.get("wheelbase_mm"), " mm")),
    )
    return ("Kích thước", ", ".join(values)) if values else None


def _powertrain_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Động cơ & Vận hành: công suất, mô-men xoắn, dẫn động, quãng đường/lần sạc.

    "Dẫn động" không có cột trong catalog nên không xuất hiện; ba mục còn lại đọc
    thẳng từ `cars`/`motorbikes`.
    """

    range_key = "range_km" if facts.vehicle_type is VehicleType.CAR else "range_max_km"
    power = _with_unit(facts.specs.get("motor_power_kw"), " kW") or _with_unit(facts.specs.get("motor_power_w"), " W")
    values = _present(
        ("công suất", power),
        ("mô-men xoắn", _with_unit(facts.specs.get("torque_nm"), " Nm")),
        ("dung lượng pin", _with_unit(facts.specs.get("battery_capacity_kwh"), " kWh")),
        ("quãng đường mỗi lần sạc", _with_unit(facts.specs.get(range_key), " km")),
        ("tốc độ tối đa", _with_unit(facts.specs.get("max_speed_kmh"), " km/h")),
    )
    return ("Động cơ & Vận hành", ", ".join(values)) if values else None


def _suspension_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Hệ thống treo trước/sau — chưa có cột trong catalog."""

    values = _present(
        ("trước", _as_text(facts.specs.get("suspension_front"))),
        ("sau", _as_text(facts.specs.get("suspension_rear"))),
    )
    return ("Hệ thống treo", ", ".join(values)) if values else None


def _air_conditioning_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Hệ thống điều hoà — chưa có cột nào trong catalog.

    CHỈ dữ liệu điều hoà thật. Trước đây dòng này gánh thêm nhóm tiện nghi
    (`PANORAMIC_ROOF`) cho khỏi mất chỗ, và khách hỏi "vf5 điều hòa loại gì"
    nhận về "Hệ thống điều hòa: Cửa sổ trời toàn cảnh" — cửa sổ trời không phải
    điều hoà, và dán nhãn sai còn tệ hơn bỏ trống.

    Cửa sổ trời vẫn trả lời được: nó có câu hỏi field riêng (`SUNROOF`) và là
    ứng viên cho câu điểm nổi bật ở đoạn mở đầu.
    """

    value = _as_text(facts.specs.get("air_conditioning"))
    return ("Hệ thống điều hòa", value) if value else None


def _infotainment_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Màn hình & Giải trí — hiện chỉ dựng được từ nhóm tính năng SMART_FEATURE.

    Catalog không lưu kích thước màn hình, số loa hay cổng USB, nên những mục đó
    vắng mặt thay vì được đoán.
    """

    values = _present(
        ("màn hình", _with_unit(facts.specs.get("screen_size_inch"), " inch")),
        ("cổng sạc", _as_text(facts.specs.get("charging_port"))),
    )
    values.extend(_feature_names(facts, _INFOTAINMENT_CODES))
    return ("Màn hình & Giải trí", ", ".join(values)) if values else None


def _safety_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """An toàn: viết tắt + tên đầy đủ ngắn gọn, KHÔNG giải thích dài từng mục."""

    names = [_with_glossary(name) for name in _feature_names(facts, _SAFETY_CODES)]
    return ("Trang bị an toàn", ", ".join(names)) if names else None


def _exterior_colour_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Màu ngoại thất, tách màu cơ bản / nâng cao — chưa có bảng màu trong catalog."""

    values = _present(
        ("cơ bản", _as_text(facts.specs.get("exterior_colours_standard"))),
        ("nâng cao", _as_text(facts.specs.get("exterior_colours_premium"))),
    )
    return ("Màu sắc ngoại thất", ", ".join(values)) if values else None


def _interior_colour_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Màu nội thất — chưa có bảng màu trong catalog."""

    value = _as_text(facts.specs.get("interior_colours"))
    return ("Màu nội thất", value) if value else None


def _price_value(facts: VehicleFacts) -> str:
    """Giá trị của mục "Giá bán", đã kèm tình trạng VAT.

    Giá `None` nghĩa là chưa có bảng giá hiệu lực — nói đúng như vậy, tuyệt đối
    không suy ra từ mẫu khác (mục 6.8: LLM/hệ thống không bịa số).
    """

    if facts.starting_price_vnd is None:
        return "hiện chưa có giá công bố hiệu lực."
    return f"từ {format_vnd(facts.starting_price_vnd)} ({VAT_NOTE})."


def _price_field(facts: VehicleFacts) -> tuple[str, str] | None:
    """Cặp (nhãn, giá trị) của giá bán, cho câu trả lời chỉ hỏi riêng giá."""

    return ("Giá bán", _price_value(facts))


def _price_phrase(facts: VehicleFacts) -> str:
    """Cụm giá gọn cho dòng tóm tắt khi khách hỏi nhiều xe cùng lúc."""

    if facts.starting_price_vnd is None:
        return "chưa có giá công bố hiệu lực"
    return f"từ {format_vnd(facts.starting_price_vnd)}"


def _unresolved_note(unmatched: Sequence[str], ambiguous: Sequence[str]) -> str:
    """Phần nói về tên xe không khớp / khớp nhiều bản, gộp về cuối một lần duy nhất."""

    parts = []
    if ambiguous:
        names = ", ".join(f"'{name}'" for name in ambiguous)
        parts.append(f"Với {names} thì VinFast có nhiều phiên bản, Quý khách đang hỏi bản nào ạ?")
    if unmatched:
        names = ", ".join(f"'{name}'" for name in unmatched)
        parts.append(f"Em chưa tìm thấy {names} trong danh mục VinFast hiện hành.")
    return " ".join(parts)


# ── Tiện ích dựng chuỗi ───────────────────────────────────────────────────────


def _join_blocks(blocks: Iterable[str | None]) -> str:
    """Ghép khối theo đúng quy ước chung; xem `domain/reply_format.join_blocks`."""

    return join_blocks(blocks)


def _as_text(value: object) -> str | None:
    """Giá trị dùng được là chuỗi khác rỗng; `None`/rỗng bị loại khỏi bảng."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _with_unit(value: object, unit: str) -> str | None:
    """Gắn đơn vị, bỏ phần thập phân thừa ("215.00 km" → "215 km")."""

    text = _as_text(value)
    if text is None:
        return None
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text}{unit}" if text else None


def _present(*pairs: tuple[str, str | None]) -> list[str]:
    """Giữ lại các cặp có giá trị, bỏ hẳn cặp thiếu dữ liệu."""

    return [f"{label} {value}" for label, value in pairs if value is not None]


def _feature_names(facts: VehicleFacts, codes: Sequence[str]) -> list[str]:
    """Tên các tính năng xe THẬT SỰ có, theo đúng thứ tự khai trong nhóm."""

    return [name for code in codes if (name := facts.features.get(code))]


def _with_glossary(name: str) -> str:
    """Thêm tên đầy đủ NGẮN GỌN cho viết tắt; tên đã rõ nghĩa thì để nguyên."""

    for abbreviation, meaning in SAFETY_GLOSSARY.items():
        if abbreviation in name.upper() and meaning not in name.lower():
            return f"{name} ({meaning})"
    return name


__all__ = [
    "CLOSING_NOTE",
    "render_attribute_answer",
    "PRICE_HEADING",
    "SAFETY_GLOSSARY",
    "SHEET_INVITATION",
    "SPEC_HEADING",
    "VAT_NOTE",
    "format_vnd",
    "render_lookup_answer",
]


# ── Trả lời theo ĐÚNG thuộc tính khách hỏi ────────────────────────────────────
#
# Trước đây mọi câu tra cứu đều nhận cùng một bảng tổng quan: khách hỏi "vf5 màu
# gì" hay "chính sách bảo hành vf5" đều được trả giá, số chỗ và tầm hoạt động.
# Trả sang một trường dữ liệu khác không phải là trả lời thiếu — nó là trả lời
# sai, và tệ hơn im lặng vì khách tưởng đã được đáp.

#: Nhãn đọc được của từng field, dùng khi phải báo "chưa có dữ liệu".
_FIELD_LABELS: Final[dict[str, str]] = {
    "PRICE": "giá bán",
    "SEAT_COUNT": "số chỗ ngồi",
    "DIMENSIONS": "kích thước",
    "POWERTRAIN": "động cơ và vận hành",
    "RANGE": "quãng đường mỗi lần sạc",
    "SUSPENSION": "hệ thống treo",
    "AIR_CONDITIONING": "hệ thống điều hòa",
    "INFOTAINMENT": "màn hình và giải trí",
    "SAFETY": "trang bị an toàn",
    "AIRBAG": "túi khí",
    "SUNROOF": "cửa sổ trời",
    "COLOR": "màu sắc ngoại thất",
    "INTERIOR_COLOR": "màu nội thất",
    "SPECS": "thông số kỹ thuật",
    "WARRANTY": "chính sách bảo hành",
}


def render_attribute_answer(facts: VehicleFacts, attribute: str) -> str:
    """Câu trả lời chỉ cho MỘT field, kèm hai câu kết chuẩn.

    Ngắn: một đến hai câu, không kéo theo cả khối "Thông số kỹ thuật chi tiết".
    Khách hỏi số chỗ mà nhận cả động cơ, pin, màn hình và giá thì câu trả lời
    đúng vẫn nằm đâu đó trong đó, nhưng chính khách phải đi tìm.

    Không có dữ liệu đã xác minh cho field đó thì nói thẳng, và KHÔNG đắp bằng
    field khác: "em chưa có dữ liệu bảo hành" là một câu trả lời đúng, còn đưa
    giá xe ra thay thì không.
    """

    body = _field_body(facts, attribute)
    return _join_blocks([f"Dạ, về {bold(facts.display_name)}:", body, CLOSING_NOTE])


def _field_body(facts: VehicleFacts, attribute: str) -> str:
    """Nội dung của đúng một field, đã ở dạng Markdown gửi thẳng cho khách.

    Hai loại builder cùng tồn tại ở đây, và chúng KHÔNG thể gộp làm một:

    - Builder trả cặp `(nhãn, giá trị)` là các trường của bảng thông số → in
      thành một dòng `**Nhãn**: giá trị`, đúng như khi nó nằm trong bảng.
    - Builder trả câu văn (`_seat_count_answer`, `_range_answer`) trả lời bằng
      một câu hoàn chỉnh; bọc thêm nhãn vào đó chỉ tạo ra "**Số chỗ ngồi**:
      VF 5 có 5 chỗ ngồi.".
    """

    builder = _FIELD_BUILDERS.get(attribute)
    value = builder(facts) if builder is not None else None
    if isinstance(value, tuple):
        label, text = value
        return f"{bold(label)}: {text}"
    return value or _missing(facts, attribute)


def _seat_count_answer(facts: VehicleFacts) -> str | None:
    seats = _as_text(facts.specs.get("seat_count"))
    return f"{facts.display_name} có {seats} chỗ ngồi." if seats else None


def _range_answer(facts: VehicleFacts) -> str | None:
    key = "range_km" if facts.vehicle_type is VehicleType.CAR else "range_max_km"
    distance = _with_unit(facts.specs.get(key), " km")
    if distance is None:
        return None
    return f"{facts.display_name} đi được khoảng {distance} cho mỗi lần sạc đầy."


def _feature_answer(facts: VehicleFacts, code: str, label: str) -> str | None:
    """Trả lời "xe có <trang bị> không" từ cờ tính năng đã duyệt.

    Vắng mặt trong `features` KHÔNG được đọc thành "xe không có": `features` chỉ
    chứa tính năng `status='YES'` đã duyệt, nên vắng mặt có thể là chưa ai xác
    minh. Trả `None` để rơi về câu "chưa có dữ liệu" — nói "xe không có cửa sổ
    trời" khi thực ra chỉ là chưa xác minh là một khẳng định sai về sản phẩm.
    """

    name = facts.features.get(code)
    return f"{facts.display_name} có {name.lower()}." if name else None


def _sunroof_answer(facts: VehicleFacts) -> str | None:
    return _feature_answer(facts, "PANORAMIC_ROOF", "cửa sổ trời")


def _airbag_answer(facts: VehicleFacts) -> str | None:
    """Túi khí: catalog chưa có cột số túi khí lẫn feature code nào cho nó.

    Cố ý KHÔNG trả cả dòng an toàn (ABS/ESC/…) thay thế: khách hỏi túi khí mà
    nhận về phanh và cân bằng điện tử là bị lái sang chuyện khác.
    """

    del facts
    return None


def _specs_answer(facts: VehicleFacts) -> str | None:
    """Khách hỏi thẳng "thông số kỹ thuật" → cả bảng, gom theo mục lớn như bảng đầy đủ."""

    sections = [section for section in _sheet_sections(facts) if section.title != PRICE_HEADING]
    blocks = render_sections(sections)
    return "\n\n".join(blocks) if blocks else None


_FieldBuilder = Callable[[VehicleFacts], "str | tuple[str, str] | None"]

_FIELD_BUILDERS: Final[dict[str, _FieldBuilder]] = {
    "PRICE": _price_field,
    "SEAT_COUNT": _seat_count_answer,
    "DIMENSIONS": _dimensions_field,
    "POWERTRAIN": _powertrain_field,
    "RANGE": _range_answer,
    "SUSPENSION": _suspension_field,
    "AIR_CONDITIONING": _air_conditioning_field,
    "INFOTAINMENT": _infotainment_field,
    "SAFETY": _safety_field,
    "AIRBAG": _airbag_answer,
    "SUNROOF": _sunroof_answer,
    "COLOR": _exterior_colour_field,
    "INTERIOR_COLOR": _interior_colour_field,
    "SPECS": _specs_answer,
}


def _missing(facts: VehicleFacts, attribute: str) -> str:
    """Câu báo chưa có dữ liệu đã xác minh cho đúng field khách hỏi."""

    label = _FIELD_LABELS.get(attribute, "thông tin này")
    return (
        f"Em chưa có dữ liệu đã xác minh về {label} của {facts.display_name}. "
        "Em xin phép chuyển câu hỏi này tới tư vấn viên để Quý khách nhận được "
        "thông tin chính xác ạ."
    )
