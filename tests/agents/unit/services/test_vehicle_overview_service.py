"""Behaviour tests for the deterministic vehicle overview builder."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.contracts import VehicleFacts
from src.agents.domain.catalog_reply import SHEET_INVITATION
from src.agents.domain.values import VehicleType
from src.agents.domain.vehicle_overview import (
    AmbiguousVehicleResolution,
    ColorInfo,
    DimensionsInfo,
    EngineSpecs,
    EngineVariantSpecs,
    EvidenceItem,
    PriceVariant,
    ResolvedVehicleFamily,
    VehicleOverview,
    VehicleOverviewResult,
)
from src.agents.services.vehicle_overview import (
    DefaultVehicleOverviewService,
    build_vehicle_overview,
    render_overview_response,
)

ECO_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PLUS_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
HIGHLIGHT_EVIDENCE_ID = "11111111-1111-1111-1111-111111111111"
FEATURE_EVIDENCE_ID = "22222222-2222-2222-2222-222222222222"
SAFETY_EVIDENCE_ID = "33333333-3333-3333-3333-333333333333"
COLOR_EVIDENCE_ID = "44444444-4444-4444-4444-444444444444"


class BlockingOverviewSource:
    """In-memory source that cannot complete data calls before all have started."""

    def __init__(
        self,
        *,
        matches: bool = True,
        catalog_colors: ColorInfo | None = None,
        rag_colors: list[EvidenceItem] | None = None,
    ) -> None:
        self._resolved = (
            ResolvedVehicleFamily(
                vehicle_name="VF 7",
                vehicle_type=VehicleType.CAR,
                vehicle_ids=(ECO_ID, PLUS_ID),
                variant_names=("Eco", "Plus"),
            )
            if matches
            else None
        )
        self._catalog_colors = catalog_colors
        self._rag_colors = (
            rag_colors
            if rag_colors is not None
            else [EvidenceItem(content="Có màu xanh rêu", evidence_id=COLOR_EVIDENCE_ID)]
        )
        self.all_started = asyncio.Event()
        self.release = asyncio.Event()
        self.started: set[str] = set()
        self._expected = {
            "prices",
            "dimensions",
            "engines",
            "colors",
            "facts",
            "highlights",
            "features",
            "safety",
            "rag_colors",
        }

    async def resolve(self, vehicle_name: str) -> ResolvedVehicleFamily | None:
        """Resolve the configured family without blocking the fan-out."""

        return self._resolved

    async def lookup_prices(self, vehicle_ids: tuple[UUID, ...]) -> list[PriceVariant]:
        """Return the two verified variant prices after the barrier opens."""

        await self._block("prices")
        return [
            PriceVariant(
                vehicle_id=ECO_ID,
                variant_name="Eco",
                amount_vnd=Decimal("799000000"),
                price_type="LIST_PRICE",
                region_code="VN",
            ),
            PriceVariant(
                vehicle_id=PLUS_ID,
                variant_name="Plus",
                amount_vnd=Decimal("949000000"),
                price_type="LIST_PRICE",
                region_code="VN",
            ),
        ]

    async def lookup_dimensions(self, vehicle_ids: tuple[UUID, ...]) -> DimensionsInfo:
        """Return verified physical dimensions after the barrier opens."""

        await self._block("dimensions")
        return DimensionsInfo(length_mm=4545, width_mm=1890, height_mm=1636)

    async def lookup_engine_specs(self, vehicle_ids: tuple[UUID, ...]) -> EngineSpecs:
        """Return one powertrain row per variant after the barrier opens."""

        await self._block("engines")
        return EngineSpecs(
            variants=[
                EngineVariantSpecs(
                    variant_name="Eco",
                    motor_power_kw=Decimal("130"),
                    torque_nm=Decimal("250"),
                    drivetrain="FWD",
                )
            ]
        )

    async def lookup_colors(self, vehicle_ids: tuple[UUID, ...]) -> ColorInfo | None:
        """Return configured catalogue colours after the barrier opens."""

        await self._block("colors")
        return self._catalog_colors

    async def lookup_facts(self, vehicle_ids: tuple[UUID, ...]) -> list[VehicleFacts]:
        """Return lookup facts for downstream quote handling after the barrier opens."""

        await self._block("facts")
        return [
            VehicleFacts(
                vehicle_id=ECO_ID,
                display_name="VF 7 Eco",
                vehicle_type=VehicleType.CAR,
                starting_price_vnd=Decimal("799000000"),
                specs={"seat_count": 5},
            )
        ]

    async def retrieve(self, vehicle_ids: tuple[UUID, ...], *, topic: str) -> list[EvidenceItem]:
        """Return topic-specific RAG evidence after the barrier opens."""

        label, item = {
            "highlights": (
                "highlights",
                EvidenceItem(content="Thiết kế hiện đại", evidence_id=HIGHLIGHT_EVIDENCE_ID),
            ),
            "features": (
                "features",
                EvidenceItem(content="Màn hình trung tâm", evidence_id=FEATURE_EVIDENCE_ID),
            ),
            "safety": (
                "safety",
                EvidenceItem(content="Hỗ trợ phanh khẩn cấp", evidence_id=SAFETY_EVIDENCE_ID),
            ),
        }.get(topic, ("rag_colors", None))
        await self._block(label)
        return [item] if item is not None else self._rag_colors

    async def _block(self, label: str) -> None:
        self.started.add(label)
        if self.started == self._expected:
            self.all_started.set()
        await self.release.wait()


async def _build_after_all_lookups_start(
    source: BlockingOverviewSource,
) -> VehicleOverviewResult:
    """Release the observable fan-out barrier and return its completed result."""

    task = asyncio.create_task(build_vehicle_overview("VF 7", source))
    try:
        await asyncio.wait_for(source.all_started.wait(), timeout=0.5)
        assert not task.done()
    finally:
        source.release.set()
    return await task


@pytest.mark.asyncio
async def test_builder_fans_out_details_and_rag_before_rendering_evidence() -> None:
    """A sequential lookup would fail to open this source's all-started barrier."""

    result = await _build_after_all_lookups_start(BlockingOverviewSource())

    assert result.overview is not None
    assert result.answer is not None
    assert result.lookup_facts[0].display_name == "VF 7 Eco"
    # [A7-6] Format chuẩn: đoạn mở đầu → các mục lớn đánh số, tên trường in đậm →
    # "Giá bán" → đoạn mời. Disclaimer cũ đã bỏ theo UX post-pitch.
    assert "1. **Thông số kỹ thuật**:" in result.answer
    assert "2. **Nội thất & Tiện nghi**:" in result.answer
    assert "**Tiện nghi**: Màn hình trung tâm" in result.answer
    assert "evidence_id" not in result.answer
    # Không câu mời/câu hỏi nào trong bảng tổng quan: `act._vehicle_qa` nối ĐÚNG
    # MỘT câu kết — bảng tự kết thêm lời mời là khách nhận hai lời mời liền nhau.
    assert SHEET_INVITATION not in result.answer
    assert "?" not in result.answer
    # Mỗi nhóm đúng MỘT dòng bullet, không phải một đoạn văn trong bullet.
    bullets = [line for line in result.answer.splitlines() if line.startswith("* ")]
    assert bullets == sorted(set(bullets), key=bullets.index)  # không lặp nội dung
    assert all(bullet.startswith("* **") and "**: " in bullet for bullet in bullets)
    # Chỉ trình bày MỘT phiên bản mặc định, không gộp Eco lẫn Plus vào một dòng.
    assert result.answer.count("**Giá bán**:") == 1
    assert result.overview.colors == ColorInfo(
        evidence_items=[EvidenceItem(content="Có màu xanh rêu", evidence_id=COLOR_EVIDENCE_ID)]
    )


@pytest.mark.asyncio
async def test_builder_omits_colors_when_catalog_and_rag_colors_are_empty() -> None:
    """An empty colour DTO must not masquerade as an available colour section."""

    result = await _build_after_all_lookups_start(BlockingOverviewSource(catalog_colors=ColorInfo(), rag_colors=[]))

    assert result.overview is not None
    assert result.overview.colors is None
    assert result.answer is not None
    assert "4. Màu sắc" not in result.answer


@pytest.mark.asyncio
async def test_builder_uses_rag_colors_when_catalog_colors_are_empty() -> None:
    """Ignoring RAG evidence behind an empty catalogue DTO loses available colour data."""

    result = await _build_after_all_lookups_start(BlockingOverviewSource(catalog_colors=ColorInfo()))

    assert result.overview is not None
    assert result.overview.colors == ColorInfo(
        evidence_items=[EvidenceItem(content="Có màu xanh rêu", evidence_id=COLOR_EVIDENCE_ID)]
    )
    assert result.answer is not None
    # Dữ liệu màu từ RAG được GIỮ trong `overview` (guardrail A6-1 và người duyệt
    # A7 vẫn đối chiếu được), nhưng KHÔNG lên dòng "Màu sắc ngoại thất" gửi khách:
    # đo trên dữ liệu thật, mẩu RAG gắn nhãn "màu" của VF 5 lại là câu nói về
    # khoang nội thất. Dòng màu chỉ nhận tên màu deterministic từ catalog.
    assert "Màu sắc ngoại thất" not in result.answer
    assert COLOR_EVIDENCE_ID not in result.answer


def test_renderer_omits_empty_safety_without_a_missing_data_placeholder() -> None:
    """Adding a safety placeholder would make an absent catalog value misleading."""

    overview_without_safety = VehicleOverview(vehicle_name="VF 7")

    answer = render_overview_response(overview_without_safety)

    assert "An toàn" not in answer
    # Chỉ mục GIÁ được nói thẳng là chưa có số liệu (spec: không bịa số); các mục
    # khác thiếu dữ liệu thì bỏ hẳn, không chèn placeholder.
    assert all("chưa có" not in line.casefold() for line in answer.splitlines() if "Giá bán" not in line)


def test_renderer_names_the_vehicle_in_its_opening_copy() -> None:
    """Dùng lại y nguyên một đoạn mở đầu cho hai mẫu xe là lỗi lặp nội dung.

    Bảng tổng quan KHÔNG tự kết bằng câu mời: câu kết duy nhất do `act` nối vào.
    """

    vf7_answer = render_overview_response(VehicleOverview(vehicle_name="VF 7"))
    vf9_answer = render_overview_response(VehicleOverview(vehicle_name="VF 9"))

    assert vf7_answer.splitlines()[0] != vf9_answer.splitlines()[0]
    assert SHEET_INVITATION not in vf7_answer
    assert SHEET_INVITATION not in vf9_answer


@pytest.mark.asyncio
async def test_default_service_delegates_unmatched_vehicle_to_builder() -> None:
    """Dropping the delegated result would hide an unresolved customer vehicle name."""

    source = BlockingOverviewSource(matches=False)
    service = DefaultVehicleOverviewService(source)

    result = await service.answer("VF Không Tồn Tại", session_id="session-1")

    assert result.unmatched == ("VF Không Tồn Tại",)
    assert result.overview is None
    assert result.answer is None


@pytest.mark.asyncio
async def test_builder_preserves_an_ambiguous_vehicle_resolution() -> None:
    """The overview path must not silently choose one of multiple families."""

    source = BlockingOverviewSource(matches=False)
    source._resolved = AmbiguousVehicleResolution(vehicle_name="VF 7")

    result = await build_vehicle_overview("VF 7", source)

    assert result.ambiguous == ("VF 7",)
    assert result.unmatched == ()
    assert result.overview is None


def test_renderer_labels_duplicate_variant_prices_by_region() -> None:
    """Regional rows for one variant must remain distinguishable to customers."""

    overview = VehicleOverview(
        vehicle_name="VF 7",
        price_variants=[
            PriceVariant(
                vehicle_id=ECO_ID,
                variant_name="Eco",
                amount_vnd=Decimal("799000000"),
                price_type="STARTING_PRICE",
                region_code="HN",
            ),
            PriceVariant(
                vehicle_id=ECO_ID,
                variant_name="Eco",
                amount_vnd=Decimal("809000000"),
                price_type="STARTING_PRICE",
                region_code="HCM",
            ),
        ],
    )

    answer = render_overview_response(overview)

    # [A7-6] Format chuẩn có ĐÚNG một mục "Giá bán" cho phiên bản mặc định.
    # Liệt kê từng vùng giá là format cũ; giữ nó lại thì mục giá lại thành một
    # danh sách con, đúng thứ format mới sinh ra để bỏ.
    assert answer.count("**Giá bán**:") == 1
    assert "**Giá bán**: từ 799.000.000 đồng (đã bao gồm VAT)." in answer
    assert "809.000.000" not in answer
