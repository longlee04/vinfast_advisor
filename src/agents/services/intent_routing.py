"""[A4-1] Resolve vehicle mentions, then read catalog facts by `vehicle_id`.

`CATALOG_LOOKUP` resolves identity without hard-filtering user needs or calling
an LLM. Exact matches produce facts; unknown and ambiguous mentions remain
unresolved instead of being guessed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final
from uuid import UUID

from src.agents.contracts import VehicleFacts, VehicleMatch
from src.agents.domain.catalog_reply import render_attribute_answer, render_lookup_answer
from src.agents.domain.intent_reconciliation import is_named_model_listing_request, is_test_drive_request
from src.agents.domain.on_road_pending import pending_for_on_road_vehicle
from src.agents.domain.pricing_intent import PricingIntent, classify_pricing_intent
from src.agents.domain.test_drive import pending_for_test_drive_vehicle
from src.agents.domain.vehicle_overview import VehicleAttribute, classify_query_attribute
from src.agents.ports import CatalogReadPort


class IntentRoutingServiceImpl:
    """Route catalog lookup mentions through deterministic catalog contracts."""

    def __init__(self, catalog: CatalogReadPort) -> None:
        self._catalog = catalog

    async def _grouped(self, mentions: Sequence[str], user_message: str = "") -> dict[str, list[VehicleMatch]]:
        grouped: dict[str, list[VehicleMatch]] = {mention: [] for mention in mentions}
        for mention in mentions:
            matches = await self._catalog.resolve_vehicle_names([mention])
            if not matches:
                matches = await self._salvage(mention, user_message)
            grouped[mention].extend(matches)
        return grouped

    async def _salvage(self, mention: str, user_message: str) -> list[VehicleMatch]:
        """Cứu một mention bị bước trích LLM cắt cụt.

        Đo được trên hệ thống thật: "giá lăn bánh vf 5" làm bước trích trả về
        `"vf"` — rơi mất số hiệu, nên không khớp xe nào và khách nhận "chưa tìm
        thấy 'vf'". Cùng câu viết liền ("vf5") hoặc đổi trật tự ("vf 5 giá bao
        nhiêu") lại trích đúng.

        Cách cứu: tìm lại chính mention đó trong câu KHÁCH ĐÃ VIẾT rồi nối thêm
        tối đa hai từ liền sau. Đây KHÔNG phải đoán danh tính xe (điều A4-1 cấm):
        mọi ký tự đều lấy từ câu của khách, và chỉ nhận khi chuỗi mở rộng khớp
        ĐÚNG MỘT xe. Khớp nhiều xe thì bỏ, để nhánh mập mờ hỏi lại như cũ.
        """

        needle = " ".join(mention.split()).casefold()
        tokens = " ".join(user_message.split()).casefold().split()
        if not needle or not tokens:
            return []
        for start, token in enumerate(tokens):
            if token != needle and not needle.startswith(token):
                continue
            for extra in (1, 2):
                candidate = " ".join(tokens[start : start + 1 + extra])
                if candidate == needle:
                    continue
                matches = await self._catalog.resolve_vehicle_names([candidate])
                if len(matches) == 1:
                    return matches
        return []

    async def resolve_vehicle_mentions(self, mentions: Sequence[str], user_message: str = "") -> list[UUID]:
        """Return one vehicle id per mention that resolves to a single model."""
        grouped = await self._grouped(mentions, user_message)
        return [chosen.vehicle_id for matches in grouped.values() if (chosen := _default_variant(matches)) is not None]

    async def ambiguous(self, mentions: Sequence[str], user_message: str = "") -> list[str]:
        """Return mentions that match several DIFFERENT models.

        Nhiều PHIÊN BẢN của cùng một dòng ("VF 6 Eco" / "VF 6 Plus") không còn
        tính là mập mờ: format trả lời chuẩn trình bày đúng một phiên bản, nên
        hỏi lại khách "bản nào ạ" trước khi nói được câu nào về VF 6 là bắt họ
        trả lời một câu hỏi mà chính họ đang đi tìm câu trả lời cho nó.
        """

        grouped = await self._grouped(mentions, user_message)
        return [mention for mention, matches in grouped.items() if _spans_models(matches)]

    async def lookup_facts(
        self, mentions: Sequence[str], user_message: str = ""
    ) -> tuple[list[VehicleFacts], list[str]]:
        """Return resolved facts and mentions absent from catalog."""
        if not mentions:
            return [], []

        grouped = await self._grouped(mentions, user_message)
        include_all_variants = is_named_model_listing_request(user_message)
        selected_matches = [
            match
            for matches in grouped.values()
            for match in _variants_for_lookup(matches, include_all=include_all_variants)
        ]
        resolved_ids = list(dict.fromkeys(match.vehicle_id for match in selected_matches))
        unmatched = [mention for mention, matches in grouped.items() if not matches]
        facts = await self._catalog.vehicle_facts(resolved_ids) if resolved_ids else []
        return facts, unmatched


def _spans_models(matches: Sequence[VehicleMatch]) -> bool:
    """Các kết quả có thuộc nhiều DÒNG xe khác nhau không."""

    return len({match.model_name for match in matches}) > 1


def _default_variant(matches: Sequence[VehicleMatch]) -> VehicleMatch | None:
    """Phiên bản mặc định để trình bày, hoặc `None` khi phải hỏi lại khách.

    [GIẢ ĐỊNH] Không có cột nào đánh dấu "bản phổ biến nhất", nên lấy bản ĐẦU
    TIÊN theo thứ tự dữ liệu — `resolve_vehicle_names` sắp theo
    `model_name, variant_name, vehicle_id` nên thứ tự này ổn định giữa các lần
    gọi, không phụ thuộc thứ tự chèn của Postgres.

    Khớp nhiều DÒNG xe thì vẫn trả `None`: chọn bừa một dòng là đoán danh tính
    xe, đúng thứ A4-1 cấm. Chỉ nhiều phiên bản của cùng một dòng mới được chọn hộ.
    """

    if not matches or _spans_models(matches):
        return None
    return matches[0]


def _variants_for_lookup(matches: Sequence[VehicleMatch], *, include_all: bool) -> Sequence[VehicleMatch]:
    """Select every requested family variant, otherwise the stable default variant."""

    if not matches or _spans_models(matches):
        return ()
    if include_all:
        return matches
    chosen = _default_variant(matches)
    return (chosen,) if chosen is not None else ()


def render_catalog_answer(
    facts: Sequence[VehicleFacts],
    unmatched: Sequence[str] = (),
    ambiguous: Sequence[str] = (),
    user_message: str = "",
) -> str | None:
    """Câu trả lời tra cứu, THEO ĐÚNG thuộc tính khách hỏi.

    Khách hỏi một thuộc tính cụ thể ("vf5 màu gì", "chính sách bảo hành vf5") thì
    chỉ nhận đúng thuộc tính đó — kể cả khi câu trả lời là "chưa có dữ liệu đã
    xác minh". Trước đây mọi câu tra cứu đều nhận cùng một bảng tổng quan, nên
    hỏi màu lại được trả giá và tầm hoạt động: đó không phải trả lời thiếu mà là
    trả lời sai.

    Chỉ áp dụng khi resolve được ĐÚNG MỘT xe và không còn tên nào chưa khớp —
    câu trả lời một thuộc tính không có chỗ để nói về những tên xe còn dang dở.
    """

    attribute = classify_query_attribute(user_message)
    if len(facts) == 1 and not unmatched and not ambiguous and attribute in _SCOPED_ATTRIBUTES:
        return render_attribute_answer(facts[0], attribute.value)
    return render_lookup_answer(facts, unmatched, ambiguous)


#: Xin lái thử mà chưa có mẫu nào để đặt.
#:
#: Đây là câu duy nhất giữ cho lượt KHÔNG rơi về chấm điểm tư vấn. Khách gõ
#: *"đăng ký lái thử"* ngay từ đầu phiên thì không có tên xe ở đâu cả — không
#: trong câu, không trong chặng sau đề xuất. Đoán bừa một mẫu là hẹn khách tới
#: showroom xem một chiếc họ không hỏi; im lặng thì lượt chết. Hỏi lại là kết
#: cục đúng duy nhất còn lại.
#: Xin tính giá lăn bánh mà chưa có mẫu nào.
#:
#: Cùng lẽ với `ASK_WHICH_VEHICLE_FOR_TEST_DRIVE`: đoán bừa một mẫu là báo giá
#: chiếc khách không hỏi — sai ở đây tốn tiền thật của họ. Im lặng thì lượt chết,
#: mà đo trên prod thì nó còn tệ hơn im lặng: bảng điểm chạy lại và khách nhận
#: về ba chiếc xe mới toanh.
ASK_WHICH_VEHICLE_FOR_ON_ROAD_PRICE: Final[str] = "Dạ em tính giá lăn bánh ngay ạ. Anh/chị muốn tính cho mẫu nào ạ?"


ASK_WHICH_VEHICLE_FOR_TEST_DRIVE: Final[str] = "Dạ em sắp xếp lái thử ngay ạ. Anh/chị muốn lái thử mẫu nào ạ?"


def render_test_drive_answer(vehicle_name: str) -> str:
    """Câu xác nhận khi khách chốt một mẫu xe và xin đặt lịch lái thử."""
    return (
        f"Dạ đã ghi nhận anh/chị chốt {vehicle_name} và muốn đặt lịch lái thử ạ. "
        "Anh/chị cho em biết showroom và thời gian mong muốn, em sẽ sắp xếp và có "
        "tư vấn viên liên hệ hỗ trợ ạ."
    )


#: Field có câu trả lời riêng. `OVERVIEW` và `UNKNOWN` cố ý vắng mặt: cả hai đều
#: có nghĩa "cho xem tổng quan", tức đúng bảng đầy đủ mặc định.
_SCOPED_ATTRIBUTES: frozenset[VehicleAttribute] = frozenset(
    set(VehicleAttribute) - {VehicleAttribute.OVERVIEW, VehicleAttribute.UNKNOWN}
)

#: `is_test_drive_request` re-export từ `domain/intent_reconciliation` để
#: `nodes/route_intent` dùng được mà không import trực tiếp `domain/` (mục 6.5b).
#:
#: `classify_pricing_intent`/`PricingIntent` cùng lý do, cho `nodes/classify_scope`:
#: bản vá 2026-08-27 import thẳng `domain/pricing_intent` vào node và
#: `tests/agents/integration/test_graph_boundary` bắt được — đây là ĐÚNG một
#: dòng re-export thay vì một bản sao thứ hai của phép đọc.
__all__ = [
    "IntentRoutingServiceImpl",
    "PricingIntent",
    "ASK_WHICH_VEHICLE_FOR_ON_ROAD_PRICE",
    "ASK_WHICH_VEHICLE_FOR_TEST_DRIVE",
    "classify_pricing_intent",
    "pending_for_on_road_vehicle",
    "pending_for_test_drive_vehicle",
    "is_test_drive_request",
    "render_catalog_answer",
    "render_test_drive_answer",
]
