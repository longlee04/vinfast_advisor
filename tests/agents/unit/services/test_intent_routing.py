"""[A4-1] CATALOG_LOOKUP resolve theo danh tính, đọc facts catalog."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import FilterCriteria, VehicleFacts, VehicleMatch
from src.agents.domain.values import VehicleType
from src.agents.services.intent_routing import IntentRoutingServiceImpl

VF8 = uuid4()
VF8_PLUS = uuid4()
VF9 = uuid4()


class FakeCatalog:
    """Fake `CatalogReadPort` với dữ liệu cứng và bộ đếm facts."""

    def __init__(self, matches: dict[str, list[VehicleMatch]]) -> None:
        self.matches = matches
        self.facts_calls = 0

    async def hard_filter(self, criteria: FilterCriteria) -> list[UUID]:
        raise AssertionError("CATALOG_LOOKUP không được chạm hard filter theo nhu cầu")

    async def differentiators(self, vehicle_ids: list[UUID]) -> list[str]:
        return []

    async def resolve_vehicle_names(self, mentions: Sequence[str]) -> list[VehicleMatch]:
        found: list[VehicleMatch] = []
        for mention in mentions:
            found.extend(self.matches.get(mention, []))
        return found

    async def vehicle_facts(self, vehicle_ids: Sequence[UUID]) -> list[VehicleFacts]:
        self.facts_calls += 1
        return [
            VehicleFacts(
                vehicle_id=vehicle_id,
                display_name="VF 8",
                vehicle_type=VehicleType.CAR,
                starting_price_vnd=Decimal(1_200_000_000),
                specs={"seat_count": 5, "range_km": 420},
            )
            for vehicle_id in vehicle_ids
        ]


def _catalog() -> FakeCatalog:
    """ "VF" khớp hai DÒNG xe khác nhau; "VF 8" khớp hai PHIÊN BẢN cùng một dòng.

    Hai ca đó cần hai hành vi trái ngược nhau (A7-6): nhiều dòng thì phải hỏi
    lại khách, còn nhiều phiên bản thì chọn bản mặc định và trình bày luôn.
    """

    return FakeCatalog(
        {
            "VF 8": [VehicleMatch(VF8, "VF 8", VehicleType.CAR, model_name="VF 8")],
            "VF 8 family": [
                VehicleMatch(VF8, "VF 8 Eco", VehicleType.CAR, model_name="VF 8"),
                VehicleMatch(VF8_PLUS, "VF 8 Plus", VehicleType.CAR, model_name="VF 8"),
            ],
            "VF": [
                VehicleMatch(VF8, "VF 8", VehicleType.CAR, model_name="VF 8"),
                VehicleMatch(VF9, "VF 9", VehicleType.CAR, model_name="VF 9"),
            ],
        }
    )


@pytest.mark.asyncio
async def test_named_vehicle_returns_catalog_facts() -> None:
    facts, unmatched = await IntentRoutingServiceImpl(_catalog()).lookup_facts(["VF 8"])

    assert facts[0].starting_price_vnd == Decimal(1_200_000_000)
    assert unmatched == []


@pytest.mark.asyncio
async def test_lookup_loads_specs_by_resolved_id() -> None:
    catalog = _catalog()

    facts, _ = await IntentRoutingServiceImpl(catalog).lookup_facts(["VF 8"])

    assert catalog.facts_calls == 1
    assert facts[0].specs["range_km"] == 420


@pytest.mark.asyncio
async def test_unknown_vehicle_is_reported() -> None:
    facts, unmatched = await IntentRoutingServiceImpl(_catalog()).lookup_facts(["VF 99"])

    assert facts == []
    assert unmatched == ["VF 99"]


@pytest.mark.asyncio
async def test_a_mention_spanning_several_models_is_flagged_ambiguous() -> None:
    """Chọn bừa một DÒNG xe là đoán danh tính — vẫn phải hỏi lại khách."""

    assert await IntentRoutingServiceImpl(_catalog()).ambiguous(["VF"]) == ["VF"]


@pytest.mark.asyncio
async def test_a_mention_spanning_several_models_produces_no_facts() -> None:
    facts, _ = await IntentRoutingServiceImpl(_catalog()).lookup_facts(["VF"])

    assert facts == []


@pytest.mark.asyncio
async def test_several_variants_of_one_model_resolve_to_a_default() -> None:
    """[A7-6] Nhiều phiên bản cùng một dòng KHÔNG còn là mập mờ.

    Format trả lời chuẩn trình bày đúng một phiên bản, nên hỏi "bản nào ạ" trước
    khi nói được câu nào về VF 8 là bắt khách trả lời chính câu họ đang đi hỏi.
    """

    routing = IntentRoutingServiceImpl(_catalog())

    assert await routing.ambiguous(["VF 8 family"]) == []
    facts, unmatched = await routing.lookup_facts(["VF 8 family"])
    assert unmatched == []
    assert [fact.vehicle_id for fact in facts] == [VF8]  # bản đầu tiên theo dữ liệu


@pytest.mark.asyncio
async def test_explicit_family_listing_returns_every_current_variant() -> None:
    """Words such as "tất cả các mẫu" must expand one family, not the whole catalog."""

    routing = IntentRoutingServiceImpl(_catalog())

    facts, unmatched = await routing.lookup_facts(["VF 8 family"], "tất cả các mẫu VF8 hiện tại")

    assert unmatched == []
    assert [fact.vehicle_id for fact in facts] == [VF8, VF8_PLUS]


@pytest.mark.asyncio
async def test_specific_attribute_does_not_expand_every_family_variant() -> None:
    """Words such as "hiện có" are not enough to turn an attribute lookup into a list."""

    routing = IntentRoutingServiceImpl(_catalog())

    facts, unmatched = await routing.lookup_facts(["VF 8 family"], "VF8 hiện có những màu gì?")

    assert unmatched == []
    assert [fact.vehicle_id for fact in facts] == [VF8]


@pytest.mark.asyncio
async def test_empty_mentions_avoid_catalog_reads() -> None:
    catalog = _catalog()

    facts, unmatched = await IntentRoutingServiceImpl(catalog).lookup_facts([])

    assert (facts, unmatched, catalog.facts_calls) == ([], [], 0)


@pytest.mark.asyncio
async def test_resolve_vehicle_mentions_returns_ids_in_input_order() -> None:
    catalog = FakeCatalog(
        {
            "VF 8": [VehicleMatch(VF8, "VF 8", VehicleType.CAR)],
            "VF 9": [VehicleMatch(VF9, "VF 9", VehicleType.CAR)],
        }
    )

    assert await IntentRoutingServiceImpl(catalog).resolve_vehicle_mentions(["VF 9", "VF 8"]) == [VF9, VF8]


@pytest.mark.asyncio
async def test_a_truncated_mention_is_salvaged_from_the_customers_own_words() -> None:
    """[A7-11] Bước trích LLM cắt cụt mention, câu của khách thì không.

    Đo trên hệ thống thật: "giá lăn bánh vf 5" làm bước trích trả về `"vf"` —
    rơi mất số hiệu nên không khớp xe nào và khách nhận "chưa tìm thấy 'vf'".
    Cùng câu viết liền ("vf5") hoặc đổi trật tự ("vf 5 giá bao nhiêu") lại trích
    đúng, nên lỗi nằm ở bước trích, không nằm ở bộ resolve.
    """

    catalog = FakeCatalog(
        {
            "vf": [],
            "vf 5": [VehicleMatch(VF8, "VF 5", VehicleType.CAR, model_name="VF 5")],
        }
    )

    facts, unmatched = await IntentRoutingServiceImpl(catalog).lookup_facts(["vf"], "giá lăn bánh vf 5")

    assert unmatched == []
    assert facts


@pytest.mark.asyncio
async def test_salvage_never_invents_a_model_the_customer_did_not_write() -> None:
    """Mọi ký tự dùng để cứu đều lấy từ câu của khách.

    Câu không hề có "5" thì không được tự nối thành "vf 5" — đó mới là đoán danh
    tính xe, điều A4-1 cấm.
    """

    catalog = FakeCatalog(
        {
            "vf": [],
            "vf 5": [VehicleMatch(VF8, "VF 5", VehicleType.CAR, model_name="VF 5")],
        }
    )

    facts, unmatched = await IntentRoutingServiceImpl(catalog).lookup_facts(["vf"], "cho em hỏi vf thế nào")

    assert facts == []
    assert unmatched == ["vf"]


@pytest.mark.asyncio
async def test_salvage_stops_when_the_extension_matches_several_models() -> None:
    """Mở rộng ra nhiều dòng xe thì bỏ, để nhánh mập mờ hỏi lại như cũ."""

    catalog = FakeCatalog(
        {
            "vf": [],
            "vf 5": [
                VehicleMatch(VF8, "VF 5", VehicleType.CAR, model_name="VF 5"),
                VehicleMatch(VF9, "VF 9", VehicleType.CAR, model_name="VF 9"),
            ],
        }
    )

    facts, unmatched = await IntentRoutingServiceImpl(catalog).lookup_facts(["vf"], "giá lăn bánh vf 5")

    assert facts == []
    assert unmatched == ["vf"]
