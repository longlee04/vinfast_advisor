"""Câu CÓ/KHÔNG về một trang bị, và câu kết phải bám đúng xe vừa hỏi.

Đo trên máy 2026-09-23 (Sếp báo): "xe vf9 có trợ lý ảo không" nhận về NGUYÊN
bản mô tả VF 9 (động cơ, ghế, ADAS, giá…) — khách hỏi MỘT điều, bot đáp bằng
MỌI điều và chính điều họ hỏi thì không có trong đó. Kèm theo, câu kết còn mời
"ưng VinFast VF 2 không, hay để em so với VinFast VF 3" trong khi cả lượt đang
nói về VF 9.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, VehicleFacts, VehiclePitch
from src.agents.core import render
from src.agents.core.act import act
from src.agents.core.actions import VehicleQa
from src.agents.core.state import CoreState, Stage
from src.agents.domain.values import SlotName as N
from src.agents.domain.vehicle_overview import VehicleOverviewResult
from src.agents.services.registry import AgentServices

V9 = "99999999-9999-9999-9999-999999999999"
V3 = "33333333-3333-3333-3333-333333333333"
V2 = "22222222-2222-2222-2222-222222222222"

OVERVIEW = (
    "Dạ, VinFast VF 9 là mẫu xe thuần điện của VinFast. Xe có gói ADAS giữ làn, "
    "cảnh báo điểm mù, camera quan sát toàn cảnh, cửa sổ trời toàn cảnh."
)


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="danh mục",
            pitches=(
                VehiclePitch(vehicle_id=UUID(V9), rank=1, display_name="VinFast VF 9", pitch=""),
                VehiclePitch(vehicle_id=UUID(V3), rank=2, display_name="VinFast VF 3", pitch=""),
                VehiclePitch(vehicle_id=UUID(V2), rank=3, display_name="VinFast VF 2", pitch=""),
            ),
        )


class _Overview:
    async def answer(self, *, vehicle_name: str, session_id: str) -> VehicleOverviewResult:
        facts = VehicleFacts(
            vehicle_id=UUID(V9),
            display_name="VinFast VF 9",
            vehicle_type="CAR",
            starting_price_vnd=None,
            specs={"tầm chạy": "626 km", "trang bị an toàn": "ADAS, ABS, ESC", "tiện nghi": "ghế da, cửa sổ trời"},
        )
        return VehicleOverviewResult(overview=None, answer=OVERVIEW, lookup_facts=(facts,))


def _state() -> CoreState:
    # Bộ đề xuất CŨ là VF 3 + VF 2 — đúng hình phiên Sếp gặp.
    return CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, recommended_ids=(V3, V2), slots={N.VEHICLE_TYPE: "CAR"}
    )


async def _ask(question: str) -> Any:
    services = AgentServices(vehicle_overview=_Overview(), catalog_browse=_Catalog())
    return await act(
        VehicleQa(vehicle_id=V9, question=question),
        _state(),
        services,
        run_id=None,
        customer_id="c1",
        user_message=question,
    )


# ---------------------------------------------------------------- bộ trích thuần


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("xe vf9 có trợ lý ảo không", "trợ lý ảo"),
        ("vf8 có cửa sổ trời không ạ", "cửa sổ trời"),
        ("xe này có được trang bị ADAS không", "ADAS"),
        ("xe có tích hợp apple carplay không", "apple carplay"),
    ],
)
def test_doc_ra_trang_bi_khach_hoi(question: str, expected: str) -> None:
    assert render.asked_feature(question) == expected


@pytest.mark.parametrize(
    "question",
    ["VF 5 sạc bao lâu", "giá lăn bánh bao nhiêu", "tầm chạy của xe là bao nhiêu", ""],
)
def test_cau_khong_phai_co_khong_thi_bo_qua(question: str) -> None:
    """Câu hỏi thông số thường vẫn đi đường cũ (`spec_answer` / bảng tổng quan)."""

    assert render.asked_feature(question) == ""


def test_khong_tim_thay_thi_khong_khang_dinh_xe_KHONG_co() -> None:  # noqa: N802
    """Dữ liệu của em có thể thiếu — nói đúng mức đó, đừng khẳng định sai về sản phẩm."""

    text = render.feature_yes_no(vehicle_name="VinFast VF 9", feature="trợ lý ảo", found=False)
    assert "chưa thấy nhắc tới" in text
    assert "không có" not in text
    assert render.assert_clean(text) == text


# ---------------------------------------------------------------- trên đường thật


@pytest.mark.asyncio
async def test_hoi_co_khong_thi_tra_loi_dung_dieu_do() -> None:
    result = await _ask("xe vf9 có trợ lý ảo không")
    assert "trợ lý ảo" in result.text
    # KHÔNG đổ cả bảng mô tả.
    assert "mẫu xe thuần điện" not in result.text
    assert len(result.text) < 400


@pytest.mark.asyncio
async def test_trang_bi_co_that_thi_tra_loi_CO() -> None:  # noqa: N802
    result = await _ask("xe vf9 có cửa sổ trời không")
    assert "VinFast VF 9 có cửa sổ trời" in result.text


@pytest.mark.asyncio
async def test_trang_bi_trong_bang_thong_so_cung_duoc_tinh() -> None:
    """Dữ liệu nằm ở `specs`, không chỉ ở đoạn mô tả."""

    result = await _ask("xe vf9 có ESC không")
    assert "có ESC" in result.text


@pytest.mark.asyncio
async def test_cau_ket_bam_dung_xe_vua_hoi() -> None:
    """Lượt hỏi VF 9 mà kết bằng "ưng VF 3 không" là bỏ rơi mạch của khách."""

    result = await _ask("xe vf9 có trợ lý ảo không")
    assert "VF 9" in result.text
    duoi = result.text.split("ạ.")[-1]
    assert "ưng VinFast VF 3" not in duoi


@pytest.mark.asyncio
async def test_cau_hoi_thong_so_thuong_van_ra_bang_tong_quan() -> None:
    """Đường cũ không đổi: câu không phải CÓ/KHÔNG vẫn nhận bảng tổng quan."""

    result = await _ask("cho tôi xem thông tin xe")
    assert "mẫu xe thuần điện" in result.text


# ---------------------------------------------------------------- định tuyến lượt


def _u(**kw: Any):
    from src.agents.core.state import DialogueAct, Intent, Understanding

    kw.setdefault("dialogue_act", DialogueAct.UNCLEAR)
    kw.setdefault("intent", Intent.NONE)
    return Understanding(**kw)


def test_go_thang_ten_xe_thi_tra_cuu_xe_do() -> None:
    """Sếp 2026-09-23: "nhiều lúc không cần tư vấn, người dùng gõ vf9 luôn"."""

    from src.agents.core.actions import LOOKUP_LOOKUP, Lookup
    from src.agents.core.policy import decide

    state = CoreState(session_id="s1", stage=Stage.COLLECTING)
    d = decide(state, _u(vehicle_ids=(V9,)))
    assert isinstance(d.action, Lookup)
    assert d.action.mode == LOOKUP_LOOKUP and d.action.vehicle_ids == (V9,)


def test_go_ten_xe_giua_luc_dang_treo_cau_ho_so() -> None:
    """Đo trên máy: "xe vf9" bị coi là đáp hồ sơ hỏng → hỏi lại → chạm trần → TVV."""

    from src.agents.core.actions import Lookup
    from src.agents.core.policy import decide
    from src.agents.core.state import DialogueAct, Pending, PendingKind

    pending = Pending(kind=PendingKind.SLOT, key="profile", asked_at_turn=1)
    state = CoreState(session_id="s1", stage=Stage.COLLECTING, pending=pending, ask_counts={"profile": 2})
    d = decide(state, _u(dialogue_act=DialogueAct.SLOT_ANSWER, vehicle_ids=(V9,)))
    assert isinstance(d.action, Lookup)
    assert d.state_after.pending is None


def test_hoi_trang_bi_ma_chua_neu_xe_thi_hoi_mau_nao_khong_hoi_tien() -> None:
    """"xe có trợ lý ảo không" → hỏi MẪU NÀO, không hỏi ngân sách."""

    from src.agents.core.actions import Ask
    from src.agents.core.policy import decide

    state = CoreState(session_id="s1", stage=Stage.COLLECTING)
    d = decide(state, _u(feature_asked="trợ lý ảo"))
    assert isinstance(d.action, Ask)
    assert d.action.key != "profile"


def test_hoi_trang_bi_khi_da_co_xe_dang_theo_thi_tra_loi_luon() -> None:
    from src.agents.core.actions import VehicleQa
    from src.agents.core.policy import decide

    state = CoreState(session_id="s1", stage=Stage.CHOSEN, chosen_vehicle_id=V9)
    d = decide(state, _u(feature_asked="trợ lý ảo", question="xe có trợ lý ảo không"))
    assert isinstance(d.action, VehicleQa) and d.action.vehicle_id == V9


def test_go_hai_ten_xe_thi_so_sanh() -> None:
    from src.agents.core.actions import Compare
    from src.agents.core.policy import decide

    state = CoreState(session_id="s1", stage=Stage.COLLECTING)
    d = decide(state, _u(vehicle_ids=(V9, V3)))
    assert isinstance(d.action, Compare) and d.action.vehicle_ids == (V9, V3)


def test_luot_khong_hieu_that_su_van_di_duong_cu() -> None:
    """Không tên xe, không hỏi trang bị → vẫn là đường UNCLEAR cũ."""

    from src.agents.core.actions import Ask, Reply
    from src.agents.core.policy import decide

    state = CoreState(session_id="s1", stage=Stage.COLLECTING)
    d = decide(state, _u())
    assert isinstance(d.action, Ask | Reply)
