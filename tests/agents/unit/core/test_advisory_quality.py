"""Ba lỗi chất lượng đo được trên máy thật 2026-09-23 (phiên "300 triệu đi 4 người").

1. "xe khác đắt hơn" không nới ngân sách → lượt nào cũng ra `TEMPLATE_NO_BETTER`
   kèm y nguyên hai thẻ cũ.
2. Bài dự phòng in mã máy: "theo tài liệu, chưa xác minh UNKNOWN".
3. "t ko muốn tư vấn nữa" bị đẩy tiếp đề xuất thay vì dừng.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, FilterCriteria, Recommendation, VehiclePitch
from src.agents.core.act import _fallback_vehicles, _readable_fact, _refined
from src.agents.core.actions import TEMPLATE_STOPPED, Recommend, Reply
from src.agents.core.policy import decide
from src.agents.core.state import CoreState, DialogueAct, Intent, Pending, PendingKind, Stage, Understanding
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.comparative_revision import detect_comparative_revision
from src.agents.domain.values import SlotName as N
from src.agents.domain.values import VehicleType
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"  # VF 3 — 278 triệu
V2 = "22222222-2222-2222-2222-222222222222"  # VF 2 — 188 triệu
V3 = "33333333-3333-3333-3333-333333333333"  # VF 6 — 675 triệu
RUN_ID = UUID("99999999-9999-9999-9999-999999999999")


# ---------------------------------------------------------------- 1. "đắt hơn"


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="danh mục",
            pitches=(
                VehiclePitch(
                    vehicle_id=UUID(V1), rank=1, display_name="VinFast VF 3", pitch="",
                    starting_price_vnd=Decimal("278000000"),
                ),
                VehiclePitch(
                    vehicle_id=UUID(V2), rank=2, display_name="VinFast VF 2", pitch="",
                    starting_price_vnd=Decimal("188000000"),
                ),
                VehiclePitch(
                    vehicle_id=UUID(V3), rank=3, display_name="VinFast VF 6", pitch="",
                    starting_price_vnd=Decimal("675000000"),
                ),
            ),
        )


def _criteria() -> FilterCriteria:
    return FilterCriteria(vehicle_type=VehicleType.CAR, budget_max_vnd=Decimal("300000000"))


@pytest.mark.parametrize("message", ["xe khác đắt hơn", "tư vấn thêm xe khác đắt giá hơn đi", "xe nào xịn hơn"])
def test_doc_ra_huong_dat_hon(message: str) -> None:
    revision = detect_comparative_revision(build_canonical_text(message))
    assert revision is not None and revision.pricier is True and revision.cheaper is False


@pytest.mark.asyncio
async def test_dat_hon_thi_nang_san_va_bo_tran_ngan_sach() -> None:
    """Khách xin mẫu trên tầm vừa xem: sàn = trên giá cao nhất đã xem, trần BỎ.

    Giữ trần 300 triệu là bảo đảm không mẫu nào lọt — đúng vòng lặp đo được:
    hai lượt "đắt hơn" liên tiếp đều ra "em chưa có mẫu nào khác hợp hơn".
    """

    services = AgentServices(catalog_browse=_Catalog())
    state = CoreState(session_id="s1", stage=Stage.RECOMMENDED, slots={N.VEHICLE_TYPE: "CAR"})
    criteria, revision = await _refined(
        services, state, criteria=_criteria(), refine="xe khác đắt hơn", seen_ids=(V1, V2)
    )
    assert revision is not None and revision.pricier
    assert criteria.budget_min_vnd == Decimal("278000001")
    assert criteria.budget_max_vnd is None


@pytest.mark.asyncio
async def test_re_hon_van_siet_tran_nhu_cu() -> None:
    services = AgentServices(catalog_browse=_Catalog())
    state = CoreState(session_id="s1", stage=Stage.RECOMMENDED, slots={N.VEHICLE_TYPE: "CAR"})
    criteria, revision = await _refined(
        services, state, criteria=_criteria(), refine="rẻ hơn được không", seen_ids=(V1, V2)
    )
    assert revision is not None and revision.cheaper
    assert criteria.budget_max_vnd == Decimal("187999999")
    assert criteria.budget_min_vnd is None


# ---------------------------------------------------------------- 2. mã máy lọt ra khách


class _Cell:
    def __init__(self, vehicle_id: UUID, label: str, value_text: str) -> None:
        self.vehicle_id = vehicle_id
        self.label = label
        self.value_text = value_text


class _Row:
    def __init__(self, cells: list[_Cell]) -> None:
        self.cells = cells


class _Table:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows


class _Recommendation:
    async def recommend(self, run_id: UUID, **_: Any) -> list[Recommendation]:
        return []

    async def compare(self, *, run_id: UUID, vehicle_ids: Any) -> _Table:
        return _Table(
            [
                _Row(
                    [
                        _Cell(UUID(V1), "theo tài liệu, chưa xác minh", "UNKNOWN"),
                        _Cell(UUID(V1), "theo tài liệu, chưa xác minh", "YES"),
                        _Cell(UUID(V1), "tầm chạy", "215 km"),
                    ]
                )
            ]
        )


@pytest.mark.parametrize(
    ("value", "doc_duoc"),
    [("215 km", True), ("278.000.000 đ", True), ("UNKNOWN", False), ("YES", False), ("LFP_BATTERY", False)],
)
def test_o_bang_la_ma_may_thi_khong_doc_cho_khach(value: str, doc_duoc: bool) -> None:
    assert _readable_fact("nhãn", value) is doc_duoc


@pytest.mark.asyncio
async def test_bai_du_phong_khong_in_ma_may() -> None:
    services = AgentServices(recommendation=_Recommendation())
    recommendations = [
        Recommendation(vehicle_id=UUID(V1), rank=1, reasons=["đủ 4 chỗ"], display_name="VinFast VF 3")
    ]
    vehicles = await _fallback_vehicles(services, run_id=RUN_ID, recommendations=recommendations)
    facts = dict(vehicles[0].facts)
    assert "UNKNOWN" not in str(vehicles[0].facts) and "YES" not in str(vehicles[0].facts)
    assert facts.get("tầm chạy") == "215 km"


# ---------------------------------------------------------------- 3. khách nói THÔI


def _u(act: DialogueAct, **kw: Any) -> Understanding:
    return Understanding(dialogue_act=act, intent=kw.pop("intent", Intent.NONE), **kw)


def test_khach_noi_thoi_thi_dung_khong_day_them_the() -> None:
    state = CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, intent=Intent.ADVISORY, recommended_ids=(V1, V2),
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 300_000_000},
    )
    d = decide(state, _u(DialogueAct.REJECT))
    assert isinstance(d.action, Reply) and d.action.template == TEMPLATE_STOPPED
    assert not isinstance(d.action, Recommend)
    # Không xoá mạch: khách quay lại là bộ đề xuất cũ còn nguyên.
    assert d.state_after.recommended_ids == (V1, V2)
    assert d.state_after.stage is Stage.RECOMMENDED


def test_reject_dang_tra_loi_mot_cau_treo_thi_khong_bi_doc_thanh_thoi() -> None:
    """REJECT trả lời một `pending` là câu trả lời cho câu đó, đã có đường riêng."""

    pending = Pending(kind=PendingKind.CONFIRM, key="book", options=("14h",))
    state = CoreState(session_id="s1", stage=Stage.SCHEDULING, chosen_vehicle_id=V1, pending=pending)
    d = decide(state, _u(DialogueAct.REJECT))
    assert not (isinstance(d.action, Reply) and d.action.template == TEMPLATE_STOPPED)


def test_reject_kem_slot_van_di_duong_tu_van() -> None:
    """"không, tầm 500 triệu thôi" vừa từ chối vừa cho tiêu chí — phải chạy lọc lại."""

    state = CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, intent=Intent.ADVISORY, recommended_ids=(V1,),
        slots={N.VEHICLE_TYPE: "CAR"},
    )
    d = decide(state, _u(DialogueAct.REJECT, slots={N.BUDGET_MAX_VND: 500_000_000}))
    assert not (isinstance(d.action, Reply) and d.action.template == TEMPLATE_STOPPED)
