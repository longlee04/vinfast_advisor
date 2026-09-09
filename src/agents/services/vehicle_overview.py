"""Build and render deterministic, evidence-backed vehicle overviews."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Sequence
from decimal import Decimal
from typing import Final, Protocol
from uuid import UUID

from src.agents.contracts import VehicleFacts
from src.agents.domain.catalog_reply import (
    PRICE_HEADING,
    SAFETY_GLOSSARY,
    SHEET_INVITATION,
    SPEC_HEADING,
    VAT_NOTE,
    format_vnd,
)
from src.agents.domain.reply_format import ReplySection, join_blocks, render_sections
from src.agents.domain.vehicle_details import build_vehicle_details
from src.agents.domain.vehicle_overview import (
    AmbiguousVehicleResolution,
    ColorInfo,
    DimensionsInfo,
    EngineSpecs,
    EngineVariantSpecs,
    EvidenceItem,
    PriceVariant,
    ResolvedVehicleFamily,
    VehicleAttribute,
    VehicleOverview,
    VehicleOverviewResult,
    classify_query_attribute,
)
from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS

OVERVIEW_DISCLAIMER: Final[str] = (
    "Liên hệ tư vấn viên để nhận thông tin giá và chính sách phù hợp với phiên bản bạn quan tâm."
)
_OPENING_TEMPLATES: Final[tuple[str, ...]] = (
    "Dưới đây là thông tin tổng quan về {vehicle_name}.",
    "Em tổng hợp các thông tin đã xác minh về {vehicle_name}.",
)
_CLOSING_TEMPLATES: Final[tuple[str, ...]] = (
    "Anh/chị có thể cho em biết nếu muốn tìm hiểu thêm về {vehicle_name}.",
    "Nếu cần, em có thể hỗ trợ tra cứu thêm các thông tin về {vehicle_name}.",
)


class VehicleOverviewSource(Protocol):
    """Read all catalog and RAG data needed for one vehicle-family overview."""

    async def resolve(self, vehicle_name: str) -> ResolvedVehicleFamily | AmbiguousVehicleResolution | None:
        """Resolve a customer vehicle mention into its catalog family."""

    async def lookup_prices(self, vehicle_ids: tuple[UUID, ...]) -> list[PriceVariant]:
        """Return verified list prices for the resolved variants."""

    async def lookup_dimensions(self, vehicle_ids: tuple[UUID, ...]) -> DimensionsInfo | None:
        """Return physical dimensions when the catalog has them."""

    async def lookup_engine_specs(self, vehicle_ids: tuple[UUID, ...]) -> EngineSpecs | None:
        """Return powertrain data when the catalog has it."""

    async def lookup_colors(self, vehicle_ids: tuple[UUID, ...]) -> ColorInfo | None:
        """Return deterministic catalog colour information when available."""

    async def lookup_facts(self, vehicle_ids: tuple[UUID, ...]) -> list[VehicleFacts]:
        """Return lookup facts for downstream deterministic quote handling."""

    async def retrieve(self, vehicle_ids: tuple[UUID, ...], *, topic: str) -> list[EvidenceItem]:
        """Return evidence-backed document excerpts for one overview topic."""


async def build_vehicle_overview(vehicle_name: str, source: VehicleOverviewSource) -> VehicleOverviewResult:
    """Resolve one family, collect independent details concurrently, and render it."""

    resolved = await source.resolve(vehicle_name)
    if resolved is None:
        return VehicleOverviewResult(unmatched=(vehicle_name,))
    if isinstance(resolved, AmbiguousVehicleResolution):
        return VehicleOverviewResult(ambiguous=(resolved.vehicle_name,))

    (
        prices,
        dimensions,
        engines,
        catalog_colors,
        facts,
        highlights,
        features,
        safety,
        rag_colors,
    ) = await asyncio.gather(
        source.lookup_prices(resolved.vehicle_ids),
        source.lookup_dimensions(resolved.vehicle_ids),
        source.lookup_engine_specs(resolved.vehicle_ids),
        source.lookup_colors(resolved.vehicle_ids),
        source.lookup_facts(resolved.vehicle_ids),
        source.retrieve(resolved.vehicle_ids, topic="highlights"),
        source.retrieve(resolved.vehicle_ids, topic="features"),
        source.retrieve(resolved.vehicle_ids, topic="safety"),
        source.retrieve(resolved.vehicle_ids, topic="colors"),
    )
    colors = _select_colors(catalog_colors, rag_colors)
    overview = VehicleOverview(
        vehicle_name=resolved.vehicle_name,
        price_variants=prices,
        dimensions=dimensions,
        engine_specs=engines,
        highlights=highlights,
        features=features,
        safety_systems=safety,
        colors=colors,
    )
    return VehicleOverviewResult(
        overview=overview,
        answer=render_overview_response(
            overview, approved_features=_approved_feature_names(facts), feature_groups=approved_feature_groups(facts)
        ),
        lookup_facts=tuple(facts),
    )


#: Nhóm `feature_definitions.category` → nhãn khách đọc, đúng thứ tự in.
FEATURE_GROUP_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("SAFETY", "An toàn"),
    ("COMFORT", "Tiện nghi"),
    ("SMART_FEATURE", "Công nghệ thông minh"),
    ("UTILITY", "Tiện ích vận hành"),
)


def approved_feature_groups(facts: Sequence[object]) -> tuple[tuple[str, str], ...]:
    """Toàn bộ trang bị đã duyệt, nhóm theo mục — không cắt 8 như trước (Sếp 2026-08-29).

    Xe không có `feature_categories` (nguồn cũ) → một dòng "Trang bị nổi bật" đủ danh sách.
    """

    by_group: dict[str, dict[str, str]] = {}
    for item in facts or ():
        categories = getattr(item, "feature_categories", None) or {}
        for code, name in (getattr(item, "features", None) or {}).items():
            group = str(categories.get(code) or "")
            by_group.setdefault(group, {}).setdefault(code, FEATURE_DISPLAY_LABELS.get(code) or str(name))
    if not by_group:
        return ()
    if list(by_group) == [""]:
        return (("Trang bị nổi bật", ", ".join(by_group[""].values())),)
    rows: list[tuple[str, str]] = []
    for key, label in FEATURE_GROUP_LABELS:
        names = by_group.pop(key, None)
        if names:
            rows.append((label, ", ".join(names.values())))
    for names in by_group.values():
        if names:
            rows.append(("Trang bị khác", ", ".join(names.values())))
    return tuple(rows)


def _approved_feature_names(facts: Sequence[object]) -> tuple[str, ...]:
    """Tên tính năng đã duyệt (cờ `YES`/`APPROVED`) gộp qua các phiên bản, giữ thứ tự khai."""

    names: dict[str, str] = {}
    for item in facts or ():
        for code, name in (getattr(item, "features", None) or {}).items():
            names.setdefault(code, FEATURE_DISPLAY_LABELS.get(code) or str(name))
    return tuple(names.values())


def render_overview_response(
    overview: VehicleOverview,
    approved_features: Sequence[str] = (),
    feature_groups: Sequence[tuple[str, str]] = (),
) -> str:
    """Dựng câu trả lời thông tin xe theo FORMAT CHUẨN của AI Sales Advisor.

    Cùng bố cục Markdown với `domain/catalog_reply` — khai một chỗ ở
    `domain/reply_format`, vì hai nhánh này trả lời CÙNG một câu hỏi của khách
    ("thông tin xe VF 5"), chỉ khác nguồn dữ liệu (catalog thuần vs. catalog +
    RAG). Hai bố cục khác nhau cho cùng một câu hỏi là thứ khách nhìn thấy ngay.

        <đoạn mở đầu 2-3 câu, không bullet>

        1. **Thông số kỹ thuật**:
        * **Kích thước**: <giá trị>
        * **Động cơ & Vận hành**: <giá trị>

        2. **An toàn**:
        * **Trang bị an toàn**: <giá trị>

        3. **Giá bán**: từ <số> (đã bao gồm VAT).

        <đoạn mời + 2 câu kết cố định>

    `evidence_id` KHÔNG đi ra ngoài. Nó vẫn nằm nguyên trong `VehicleOverview`
    để guardrail A6-1 và hàng đợi duyệt A7 đối chiếu — bỏ khỏi câu chữ gửi khách
    khác hẳn với bỏ khỏi dữ liệu.
    """

    return join_blocks(
        [
            _render_opening(overview),
            *render_sections(_overview_sections(overview, approved_features, feature_groups)),
            SHEET_INVITATION,
        ]
    )


def _overview_sections(
    overview: VehicleOverview,
    approved_features: Sequence[str] = (),
    feature_groups: Sequence[tuple[str, str]] = (),
) -> list[ReplySection]:
    """Các mục lớn, đúng thứ tự; mục không có trường nào có dữ liệu bị bỏ hẳn.

    Trang bị đã duyệt in ĐỦ theo nhóm trong mục "Trang bị" riêng (Sếp 2026-08-29:
    "thông tin xe chưa chi tiết"); nguồn không có nhóm thì rơi về dòng "Trang bị
    nổi bật" — cờ tính năng không cần tài liệu RAG nên mẫu như VF 5 vẫn kể được.
    """

    groups = tuple(feature_groups) or (
        (("Trang bị nổi bật", ", ".join(approved_features)),) if approved_features else ()
    )
    return [
        ReplySection(SPEC_HEADING, tuple(_technical_fields(overview))),
        ReplySection("Nội thất & Tiện nghi", tuple(_comfort_fields(overview))),
        ReplySection("Trang bị", groups),
        ReplySection("An toàn", tuple(_safety_fields(overview))),
        ReplySection("Ngoại thất", tuple(_exterior_fields(overview))),
        ReplySection(PRICE_HEADING, value=_price_value(overview.price_variants)),
    ]


def _render_opening(overview: VehicleOverview) -> str:
    """Đoạn mở đầu 2-3 câu, không bullet: phân khúc → thiết kế → 1 tiện ích.

    Mỗi vế lấy TỐI ĐA một mẩu evidence và cắt về một câu. Đổ nguyên trích đoạn
    RAG vào đây là cách format cũ phình ra và lặp lại chính nó ở phần dưới.
    """

    sentences = [f"Dạ, {overview.vehicle_name} là mẫu xe thuần điện của VinFast."]
    design = _first_sentence(overview.highlights)
    if design is not None:
        sentences.append(design)
    utility = _first_sentence(overview.features)
    if utility is not None and utility != design:
        sentences.append(utility)
    return " ".join(sentences)


def _technical_fields(overview: VehicleOverview) -> list[tuple[str, str]]:
    """Nhóm kỹ thuật: kích thước và động cơ, đọc từ catalog chứ không từ RAG.

    "Hệ thống treo" và "Hệ thống điều hòa" chưa có nguồn nào trong catalog lẫn
    RAG, nên chúng không xuất hiện — ghi "chưa có thông tin" cho đủ mục là làm
    bảng dài ra mà không thêm một dữ kiện nào.
    """

    builders = (_dimension_field, _powertrain_field)
    return [pair for build in builders if (pair := build(overview)) is not None]


def _comfort_fields(overview: VehicleOverview) -> list[tuple[str, str]]:
    """Render verified feature evidence as one concise amenity field."""

    values = tuple(
        dict.fromkeys(
            sentence.rstrip(".") for item in overview.features if (sentence := _first_sentence([item])) is not None
        )
    )
    return [("Tiện nghi", "; ".join(values))] if values else []


def _safety_fields(overview: VehicleOverview) -> list[tuple[str, str]]:
    pair = _safety_field(overview)
    return [pair] if pair is not None else []


def _exterior_fields(overview: VehicleOverview) -> list[tuple[str, str]]:
    pair = _exterior_colour_field(overview)
    return [pair] if pair is not None else []


def _dimension_field(overview: VehicleOverview) -> tuple[str, str] | None:
    """Kích thước: DxRxC, chiều dài cơ sở — gộp một dòng thay vì 5 dòng rời."""

    dimensions = overview.dimensions
    if dimensions is None:
        return None
    values = []
    lwh = [dimensions.length_mm, dimensions.width_mm, dimensions.height_mm]
    if all(value is not None for value in lwh):
        values.append(" x ".join(f"{value}" for value in lwh) + " mm")
    if dimensions.wheelbase_mm is not None:
        values.append(f"chiều dài cơ sở {dimensions.wheelbase_mm} mm")
    if dimensions.ground_clearance_mm is not None:
        values.append(f"khoảng sáng gầm {dimensions.ground_clearance_mm} mm")
    return ("Kích thước", ", ".join(values)) if values else None


def _powertrain_field(overview: VehicleOverview) -> tuple[str, str] | None:
    """Động cơ & Vận hành của ĐÚNG MỘT phiên bản mặc định.

    Format chuẩn là bảng của một phiên bản. Gộp cả VF 8 Eco lẫn Plus vào một
    bullet cho hai bộ công suất/mô-men xoắn khác nhau thì khách không biết con
    số nào thuộc bản nào.
    """

    variant = _default_engine_variant(overview.engine_specs)
    if variant is None:
        return None
    details = _engine_details(variant.motor_power_kw, variant.torque_nm, variant.drivetrain)
    details.extend(_performance_details(variant))
    return ("Động cơ & Vận hành", ", ".join(details)) if details else None


def _safety_field(overview: VehicleOverview) -> tuple[str, str] | None:
    """An toàn: viết tắt + tên đầy đủ NGẮN GỌN, rút ra từ trích đoạn tài liệu.

    Trích đoạn RAG là văn xuôi ("Ở phần hỗ trợ phanh và kiểm soát thân xe,
    VinFast VF 5 có ABS, EBD, BA, ESC và TCS"). Đổ nguyên câu vào bullet là biến
    dòng thông số thành một đoạn văn — đúng thứ format chuẩn cấm. Ở đây chỉ RÚT
    các viết tắt đã biết ra, mỗi cái kèm nghĩa ngắn.

    Viết tắt không nằm trong từ điển thì bỏ qua: đoán nghĩa hộ một chữ viết tắt
    an toàn là chỗ sai nguy hiểm nhất trong cả câu trả lời.
    """

    corpus = " ".join(item.content for item in overview.safety_systems)
    found = [
        f"{abbreviation} ({meaning})"
        for abbreviation, meaning in SAFETY_GLOSSARY.items()
        if _mentions_abbreviation(corpus, abbreviation)
    ]
    if found:
        return ("Trang bị an toàn", ", ".join(found))
    # Tài liệu của một số mẫu chỉ gọi tên đầy đủ, không dùng viết tắt nào (VF 8:
    # "kiểm soát hành trình thích ứng, hỗ trợ giữ làn..."). Bỏ trắng cả nhóm thì
    # mất thông tin an toàn thật; lấy ĐÚNG một câu là giữ được nó mà vẫn gọn.
    fallback = _first_sentence(overview.safety_systems)
    return ("Trang bị an toàn", fallback.rstrip(".")) if fallback else None


def _mentions_abbreviation(corpus: str, abbreviation: str) -> bool:
    """Khớp viết tắt theo RANH GIỚI TỪ.

    Tìm chuỗi con sẽ cho "BA" khớp vào "BAO", "ESS" khớp vào "ESSENTIAL" — và
    câu trả lời sẽ khẳng định xe có một hệ thống an toàn nó không có.
    """

    return re.search(rf"(?<![A-Za-z]){re.escape(abbreviation)}(?![A-Za-z])", corpus) is not None


def _exterior_colour_field(overview: VehicleOverview) -> tuple[str, str] | None:
    """Màu ngoại thất.

    Catalog không đánh dấu màu nào là cơ bản, màu nào nâng cao, cũng không có
    cột phụ phí — nên không tách hai nhóm đó thay vì tự gán bừa.
    """

    colors = overview.colors
    if colors is None or not colors.names:
        # CHỈ dùng tên màu deterministic từ catalog, không dùng trích đoạn RAG.
        # Đo trên dữ liệu thật: mẩu RAG được gắn nhãn "màu" của VF 5 lại là câu
        # nói về khoang nội thất và vô lăng. Đưa nó lên dòng "Màu sắc ngoại thất"
        # là khẳng định một điều sai, và sai ở đúng chỗ khách đọc để chọn màu.
        # Trích đoạn vẫn nằm trong `overview.colors` cho guardrail và người duyệt.
        return None
    return ("Màu sắc ngoại thất", ", ".join(colors.names))


def _price_value(prices: list[PriceVariant]) -> str | None:
    """Giá trị mục "Giá bán" cho phiên bản mặc định, ghi rõ tình trạng VAT."""

    if not prices:
        return None
    return f"từ {format_vnd(prices[0].amount_vnd)} ({VAT_NOTE})."


def _default_engine_variant(engine_specs: EngineSpecs | None):
    """Phiên bản mặc định để trình bày.

    [GIẢ ĐỊNH] Không có cột nào đánh dấu "bản phổ biến nhất", nên lấy bản ĐẦU
    TIÊN theo thứ tự dữ liệu. Khách hỏi rõ một phiên bản thì `resolve` đã thu về
    đúng bản đó, nên nhánh này chỉ chạy cho câu hỏi chung chung.
    """

    if engine_specs is None:
        return None
    for variant in engine_specs.variants:
        if _engine_details(variant.motor_power_kw, variant.torque_nm, variant.drivetrain):
            return variant
    return None


def _first_sentence(evidence: list[EvidenceItem]) -> str | None:
    """Câu đầu tiên của mẩu evidence đầu tiên, đã chuẩn hoá dấu chấm câu."""

    for item in evidence:
        phrase = _shorten(item.content)
        if phrase:
            return phrase if phrase.endswith(".") else f"{phrase}."
    return None


def _shorten(content: str) -> str:
    """Rút một trích đoạn về câu đầu, bỏ khoảng trắng thừa và dấu chấm cuối."""

    normalized = " ".join(content.split())
    head = normalized.split(". ")[0].strip()
    return head.rstrip(".").strip()


class DefaultVehicleOverviewService:
    """Application seam for answering a vehicle overview request."""

    def __init__(self, source: VehicleOverviewSource) -> None:
        self._source = source

    async def answer(self, vehicle_name: str, session_id: str) -> VehicleOverviewResult:
        """Build an overview; session context is reserved for future copy policy."""

        del session_id
        return await build_vehicle_overview(vehicle_name, self._source)


def is_vehicle_overview_request(message: str) -> bool:
    """Expose overview classification without leaking domain enums into graph nodes."""

    return classify_query_attribute(message) is VehicleAttribute.OVERVIEW


def _copy_index(vehicle_name: str) -> int:
    """Choose repeat-resistant copy deterministically from the vehicle name."""

    return sum((index + 1) * ord(character) for index, character in enumerate(vehicle_name)) % len(_OPENING_TEMPLATES)


def _select_colors(catalog_colors: ColorInfo | None, rag_colors: list[EvidenceItem]) -> ColorInfo | None:
    """Prefer non-empty catalog colours, then non-empty RAG colour evidence."""

    if catalog_colors is not None and (catalog_colors.names or catalog_colors.evidence_items):
        return catalog_colors
    if rag_colors:
        return ColorInfo(evidence_items=rag_colors)
    return None


def _engine_details(motor_power_kw: Decimal | None, torque_nm: Decimal | None, drivetrain: str | None) -> list[str]:
    """Render only verified values for one engine variant.

    `Decimal("100.000")` phải ra "100 kW", không phải "100.000 kW": trong cách
    đọc số của tiếng Việt, dấu chấm là phân cách hàng nghìn — "330.000 Nm" bị
    đọc thành ba trăm ba mươi nghìn Nm. `:g` không đủ vì nó giữ nguyên số chữ số
    có nghĩa mà `Numeric(10, 3)` mang theo.
    """

    details = []
    if motor_power_kw is not None:
        details.append(f"công suất {_plain_number(motor_power_kw)} kW")
    if torque_nm is not None:
        details.append(f"mô-men xoắn {_plain_number(torque_nm)} Nm")
    if drivetrain:
        details.append(f"dẫn động {drivetrain}")
    return details


def _performance_details(variant: EngineVariantSpecs) -> list[str]:
    """Pin, tầm chạy, tốc độ, sạc nhanh — từ bảng `cars`, không cần tài liệu."""

    details: list[str] = []
    if variant.battery_capacity_kwh is not None:
        details.append(f"dung lượng pin {_plain_number(variant.battery_capacity_kwh)} kWh")
    if variant.range_km is not None:
        cycle = f" ({variant.range_cycle})" if variant.range_cycle else ""
        details.append(f"quãng đường mỗi lần sạc {_plain_number(variant.range_km)} km{cycle}")
    if variant.max_speed_kmh is not None:
        details.append(f"tốc độ tối đa {_plain_number(variant.max_speed_kmh)} km/h")
    if variant.fast_charge_time_minutes is not None:
        window = ""
        if variant.fast_charge_from_percent is not None and variant.fast_charge_to_percent is not None:
            window = f" ({variant.fast_charge_from_percent}–{variant.fast_charge_to_percent}%)"
        details.append(f"sạc nhanh {variant.fast_charge_time_minutes} phút{window}")
    return details


def _plain_number(value: Decimal) -> str:
    """Bỏ phần thập phân thừa do kiểu `Numeric(p, s)` của cột mang theo."""

    normalized = value.normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


# ── Khách CHỌN một mẫu xe trong bản đề xuất ──────────────────────────────────
#
# Sếp 2026-08-26: "đề xuất xong, khách chọn xe sau đó phải được gửi thông tin xe".
# Nút "Chọn mẫu này" gửi `"Tôi chọn <tên>"` như một tin nhắn bình thường (cùng
# quy ước với `QuickReplies`), nhưng `classify_query_attribute` không xếp câu đó
# vào `OVERVIEW` nên nó rơi về nhánh tra cứu chung.
#
# Đặt Ở ĐÂY chứ không ở `domain/`: `nodes/` bị cấm import `domain/` (mục 6.5b,
# `test_graph_boundary` khoá), mà node đã import `is_vehicle_overview_request` từ
# module này rồi — hai phép nhận diện cùng phục vụ một nhánh thì nên ở cạnh nhau.
#
# Chỉ nhận diện Ý ĐỊNH, KHÔNG đọc tên xe: tên mẫu đã có bộ trích riêng
# (`vehicle_mentions` + khớp tên Lớp 2) xử lý được cả viết tắt lẫn sai chính tả.
# Viết bản đọc tên thứ hai ở đây là dựng hai bản cho cùng một thứ rồi để chúng
# lệch nhau âm thầm.


def _fold_choice(value: str) -> str:
    """Bỏ dấu + gộp khoảng trắng. Cùng kiểu với `claim_policy._fold_diacritics`."""

    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d")).strip()


#: Động từ CHỌN đứng trước tên xe. Không neo `^` vì lời chọn hay có tiền tố tự do
#: ("dạ thôi anh chọn con VF 8"); bù lại mỗi động từ phải là TỪ TRỌN VẸN (`\b`).
#: Bài học `"k"` nuốt `"khoá chống trộm"`: mẫu lỏng ở đây gán cho khách một quyết
#: định họ chưa nêu, và hệ gửi bảng thông số của chiếc xe SAI.
#:
#: `"thích"` KHÔNG có mặt: "anh thích xe màu đỏ" không phải lời chọn mẫu.
_CHOICE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:chon|lay|quyet dinh chon|chot|dat|mua)\b\s*(?:con|chiec|xe|mau|em|ban|phien ban\s*)*"
)

#: Câu ĐANG cân nhắc, xét TRƯỚC mẫu trên. "nên chọn VF 3 hay VF 5" chứa động từ
#: chọn mà là lời XIN TƯ VẤN — gửi thẳng bảng thông số một chiếc là trả lời lệch.
#: "tư vấn giúp tôi chọn xe", "chọn giúp anh đi" là NHỜ chọn, khác hẳn ĐÃ chọn.
_STILL_DECIDING_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bnen\b|\bhay\b|\bhoac\b|\?|"
    r"\bchon\s+(?:xe\s+)?(?:nao|gi)\b|"
    r"\bcai\s+nao\b|\bthe\s+nao\b|\bso sanh\b|"
    r"\bchon\s+(?:giup|ho)\b|\btu van\b|\bgoi y\b"
)


#: Từ đệm được phép đứng quanh một tên xe TRƠ TRỌI mà câu vẫn là lời chọn.
#:
#: Tập ĐÓNG, cùng khuôn với các bộ đọc đuôi khác trong `domain/`. Đuôi tự do thì
#: "VF 8 có bản nào rẻ hơn" cũng thành lời chọn, và khách hỏi giá lại nhận về
#: bảng thông số kèm lời mời lái thử.
_BARE_CHOICE_FILLER: Final[frozenset[str]] = frozenset(
    {
        "a",
        "ah",
        "aj",
        "con",
        "chiec",
        "xe",
        "mau",
        "em",
        "anh",
        "minh",
        "ban",
        "nhe",
        "nha",
        "di",
        "luon",
        "thoi",
        "the",
        "nay",
        "do",
        "phien ban",
        "ok",
        "oke",
    }
)


def is_bare_vehicle_choice(message: str, vehicle_name: str) -> bool:
    """Cả câu chỉ là TÊN XE (kèm từ đệm) — dùng RIÊNG ở chặng chờ khách chọn mẫu.

    Sếp 2026-08-26, đo trên câu thật: khách gõ đúng "VF 8" sau khi xem ba thẻ đề
    xuất. `is_vehicle_choice` đòi một ĐỘNG TỪ ("chọn", "lấy", "chốt") nên câu đó
    trả `False` và cả luồng đứng lại ở chặng chờ chọn — khách đã chỉ vào chiếc xe
    mà hệ không nhận.

    Vị từ này KHÔNG nới `is_vehicle_choice`: nới ở đó thì mọi lượt nhắc tên xe
    trong toàn hệ thống thành lời chọn, kể cả "VF 8 giá bao nhiêu". Ở đây ngữ
    cảnh đã hẹp sẵn — đang chờ khách chỉ một trong ba mẫu vừa đưa — nên một câu
    không mang gì ngoài tên xe chỉ có thể là lời chỉ vào chiếc đó.
    """

    folded = _fold_choice(message)
    name = _fold_choice(vehicle_name)
    if not folded or not name or name not in folded:
        return False
    remainder = folded.replace(name, " ")
    return all(word in _BARE_CHOICE_FILLER for word in remainder.split())


def is_vehicle_choice(message: str) -> bool:
    """Khách đang CHỐT một mẫu xe?

    Chỉ `True` cho lời chọn dứt khoát. Câu còn cân nhắc ("nên chọn VF 3 hay VF 5")
    trả `False`: ở đó khách cần so sánh, không cần bảng thông số một chiếc.
    """

    folded = _fold_choice(message)
    if _STILL_DECIDING_PATTERN.search(folded):
        return False
    return _CHOICE_PATTERN.search(folded) is not None


#: `build_vehicle_details` re-export cho `nodes/`: node bị cấm import `domain/`
#: (luật 6.5b), cùng quy ước với `is_test_drive_request` ở `intent_routing`.
__all__ = [*globals().get("__all__", []), "build_vehicle_details"]
