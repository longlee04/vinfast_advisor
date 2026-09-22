"""Cửa CAM KẾT THƯƠNG MẠI của lõi v2 (`act._commercial_guard`, plan agent-migration Bước 2).

`quote_gate` từng mồ côi (không chỗ nào trong `core/` đọc). Cắm lại ở đúng một
đường: `_pitch_text`, ngay sau `verification.verify`. Bài hứa giảm giá / ưu
đãi ngoài bảng / trả góp → đường dự phòng tất định; bài bình thường → y nguyên;
`quote_gate=None` → y nguyên (nút lùi không cần revert code).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, FilterCriteria, Recommendation, VehiclePitch
from src.agents.core.act import _commercial_guard, act
from src.agents.core.actions import Recommend
from src.agents.core.state import CoreState, Stage
from src.agents.domain.values import SlotName as N
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
RUN_ID = UUID("99999999-9999-9999-9999-999999999999")
CAR_FULL = {N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 1_000_000_000, N.PURPOSE: "đi làm", N.PASSENGER_COUNT: 5}


def _pitch(vehicle_id: str, name: str, text: str) -> VehiclePitch:
    return VehiclePitch(vehicle_id=UUID(vehicle_id), rank=1, display_name=name, pitch=text)


class _Retrieval:
    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        return [UUID(V1), UUID(V2)]

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids: Any) -> list:
        return []


class _Snapshotting:
    async def snapshot(self, *, run_id: UUID, candidate_ids: Any, assertions: Any) -> None:
        return None


class _Recommendation:
    async def recommend(self, run_id: UUID, **_: Any) -> list[Recommendation]:
        return [
            Recommendation(vehicle_id=UUID(V1), rank=1, reasons=["đủ 5 chỗ"], display_name="VinFast VF 5"),
            Recommendation(vehicle_id=UUID(V2), rank=2, reasons=["đi xa hơn"], display_name="VinFast VF 6"),
        ]


class _Synthesis:
    def __init__(self, pitches: tuple[VehiclePitch, ...]) -> None:
        self.pitches = pitches

    async def synthesize(self, **_: Any) -> tuple[VehiclePitch, ...]:
        return self.pitches


class _Verification:
    async def verify(self, *, run_id: UUID, draft_answer: str) -> bool:
        return True


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="VF 5, VF 6",
            pitches=(
                VehiclePitch(vehicle_id=UUID(V1), rank=1, display_name="VinFast VF 5", pitch=""),
                VehiclePitch(vehicle_id=UUID(V2), rank=2, display_name="VinFast VF 6", pitch=""),
            ),
        )


@dataclass(frozen=True)
class _GateConfig:
    standard_promotions: frozenset[str] = frozenset()


class _Gate:
    """Hình dáng tối thiểu của `QuoteGateServiceImpl` mà `_commercial_guard` đọc."""

    config = _GateConfig()


def _services(pitches: tuple[VehiclePitch, ...], *, gate: object | None) -> AgentServices:
    return AgentServices(
        retrieval=_Retrieval(),
        snapshotting=_Snapshotting(),
        recommendation=_Recommendation(),
        synthesis=_Synthesis(pitches),
        verification=_Verification(),
        catalog_browse=_Catalog(),
        quote_gate=gate,
    )


def _state() -> CoreState:
    return CoreState(session_id="s1", stage=Stage.COLLECTING, slots=CAR_FULL)


async def _recommend(services: AgentServices) -> str:
    result = await act(
        Recommend(), _state(), services, run_id=RUN_ID, customer_id="c1", user_message="tư vấn cho anh"
    )
    return result.text


BINH_THUONG = (
    _pitch(V1, "VinFast VF 5", "VinFast VF 5 giá từ 458 triệu, đi được 326 km, rẻ hơn VF 6 và đủ 5 chỗ."),
    _pitch(V2, "VinFast VF 6", "VinFast VF 6 đi xa hơn với 460 km mỗi lần sạc."),
)
HUA_GIAM_GIA = (
    _pitch(V1, "VinFast VF 5", "VinFast VF 5 giá 458 triệu, em giảm cho anh 20 triệu nếu chốt hôm nay."),
    _pitch(V2, "VinFast VF 6", "VinFast VF 6 đi xa hơn."),
)


@pytest.mark.asyncio
async def test_pitch_hua_giam_gia_bi_chan() -> None:
    text = await _recommend(_services(HUA_GIAM_GIA, gate=_Gate()))
    assert "giảm cho anh" not in text
    assert "VF 5" in text  # đường dự phòng vẫn là một lượt đề xuất có nội dung


@pytest.mark.asyncio
async def test_pitch_binh_thuong_di_thang() -> None:
    co_gate = await _recommend(_services(BINH_THUONG, gate=_Gate()))
    khong_gate = await _recommend(_services(BINH_THUONG, gate=None))
    assert co_gate == khong_gate
    assert "rẻ hơn VF 6" in co_gate  # so sánh số thật KHÔNG bị coi là mặc cả


@pytest.mark.asyncio
async def test_quote_gate_none_thi_di_thang() -> None:
    text = await _recommend(_services(HUA_GIAM_GIA, gate=None))
    assert "giảm cho anh 20 triệu" in text  # hành vi hôm nay, không cổng


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "draft",
    [
        "Anh có thể trả góp 0% lãi suất trong 2 năm.",
        "Hiện xe đang có ưu đãi tặng kèm bộ sạc tại nhà.",
        "Em chốt giá riêng cho anh 430 triệu.",
    ],
)
async def test_guard_chan_moi_loai_cam_ket(draft: str) -> None:
    assert await _commercial_guard(draft, _state(), AgentServices(quote_gate=_Gate())) is False


@pytest.mark.asyncio
async def test_guard_doc_bang_khuyen_mai_chuan_tu_config() -> None:
    class _GateWithPromo:
        config = _GateConfig(standard_promotions=frozenset({"tặng kèm bộ sạc tại nhà"}))

    draft = "Hiện xe đang có ưu đãi tặng kèm bộ sạc tại nhà."
    assert await _commercial_guard(draft, _state(), AgentServices(quote_gate=_GateWithPromo())) is True
    assert await _commercial_guard(draft, _state(), AgentServices(quote_gate=_Gate())) is False
