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
V4 = "44444444-4444-4444-4444-444444444444"  # VF 5 — 496 triệu
V5 = "55555555-5555-5555-5555-555555555555"  # VF 9 — 1,4 tỷ
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
async def test_re_hon_lui_mot_nac_so_voi_thu_dang_xem() -> None:
    """Khách đã bước LÊN trên trần của mình thì "rẻ hơn" lùi MỘT nấc, không rơi thẳng về đáy.

    Đo trên máy 2026-09-23: khách 400 triệu xin đắt hơn hai lượt tới VF 8, gõ
    "rẻ hơn" và bị ném về VF 3/VF 2 thay vì lùi sang VF 6/VF 5.
    """

    services = AgentServices(catalog_browse=_Catalog())
    state = CoreState(session_id="s1", stage=Stage.RECOMMENDED, slots={N.VEHICLE_TYPE: "CAR"})
    criteria, _ = await _refined(
        services,
        state,
        criteria=FilterCriteria(vehicle_type=VehicleType.CAR, budget_max_vnd=Decimal("300000000")),
        refine="rẻ hơn đi",
        seen_ids=(V3,),  # đang xem mẫu 675 triệu, trên hẳn trần 300 triệu trong slot
    )
    assert criteria.budget_max_vnd == Decimal("674999999")


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
    # Cờ `stop_asked` do cửa tất định `understand._stop_requested` bật, KHÔNG
    # suy từ `dialogue_act=REJECT`: LLM gắn REJECT cho cả "rẻ hơn đi".
    d = decide(state, _u(DialogueAct.REJECT, stop_asked=True))
    assert isinstance(d.action, Reply) and d.action.template == TEMPLATE_STOPPED
    assert not isinstance(d.action, Recommend)
    # Không xoá mạch: khách quay lại là bộ đề xuất cũ còn nguyên.
    assert d.state_after.recommended_ids == (V1, V2)
    assert d.state_after.stage is Stage.RECOMMENDED


def test_reject_dang_tra_loi_mot_cau_treo_thi_khong_bi_doc_thanh_thoi() -> None:
    """REJECT trả lời một `pending` là câu trả lời cho câu đó, đã có đường riêng."""

    pending = Pending(kind=PendingKind.CONFIRM, key="book", options=("14h",))
    state = CoreState(session_id="s1", stage=Stage.SCHEDULING, chosen_vehicle_id=V1, pending=pending)
    d = decide(state, _u(DialogueAct.REJECT, stop_asked=True))
    assert not (isinstance(d.action, Reply) and d.action.template == TEMPLATE_STOPPED)


def test_loi_xin_chinh_bi_gan_reject_thi_khong_bi_doc_thanh_thoi() -> None:
    """Đo trên máy 2026-09-23: "rẻ hơn đi" về REJECT và bot chào tạm biệt.

    Cửa dừng đọc CHÍNH lời khách, nên câu xin chỉnh giá vẫn đi đường tư vấn.
    """

    state = CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, intent=Intent.ADVISORY, recommended_ids=(V1, V2),
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 300_000_000},
    )
    d = decide(state, _u(DialogueAct.REJECT, question="rẻ hơn đi"))
    assert not (isinstance(d.action, Reply) and d.action.template == TEMPLATE_STOPPED)
    assert isinstance(d.action, Recommend) and d.action.refine == "rẻ hơn đi"


def test_reject_kem_slot_van_di_duong_tu_van() -> None:
    """"không, tầm 500 triệu thôi" vừa từ chối vừa cho tiêu chí — phải chạy lọc lại."""

    state = CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, intent=Intent.ADVISORY, recommended_ids=(V1,),
        slots={N.VEHICLE_TYPE: "CAR"},
    )
    d = decide(state, _u(DialogueAct.REJECT, stop_asked=True, slots={N.BUDGET_MAX_VND: 500_000_000}))
    assert not (isinstance(d.action, Reply) and d.action.template == TEMPLATE_STOPPED)


# ---------------------------------------------------------------- 4. xếp hạng phải biết lượt đã nới trần


@pytest.mark.parametrize(
    ("slot_budget", "criteria_max", "relaxed"),
    [
        (300_000_000, None, True),  # khách xin xe đắt hơn → trần bị BỎ
        (300_000_000, Decimal("420000000"), True),  # bậc thang tự nới +40%
        (300_000_000, Decimal("300000000"), False),  # lượt thường
        (300_000_000, Decimal("187999999"), False),  # khách xin RẺ hơn
        (None, None, False),  # khách chưa nêu ngân sách
    ],
)
def test_budget_relaxed_dung_khi_luot_co_y_vuot_tran(
    slot_budget: int | None, criteria_max: Decimal | None, relaxed: bool
) -> None:
    """`recommend` loại mọi mẫu vượt trần đọc từ slot, nên nó PHẢI biết lượt nới.

    Thiếu cờ này thì `layer1` tìm ra xe đắt hơn xong bộ xếp hạng loại sạch, và
    lượt rơi về "em chưa có mẫu nào khác hợp hơn" (đo trên máy 2026-09-23).
    """

    from src.agents.core.act import _budget_relaxed

    slots: dict[Any, Any] = {N.VEHICLE_TYPE: "CAR"}
    if slot_budget is not None:
        slots[N.BUDGET_MAX_VND] = slot_budget
    state = CoreState(session_id="s1", stage=Stage.RECOMMENDED, slots=slots)
    criteria = FilterCriteria(vehicle_type=VehicleType.CAR, budget_max_vnd=criteria_max)
    assert _budget_relaxed(state, criteria) is relaxed


# ---------------------------------------------------------------- 5. sàn giá phải có hiệu lực


class _Retrieval:
    """`layer1` CHỈ đọc trần (đúng như `catalog_reader.hard_filter`) — sàn bị bỏ qua."""

    def __init__(self) -> None:
        self.seen: list[FilterCriteria] = []

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        self.seen.append(criteria)
        return [UUID(V1), UUID(V2), UUID(V3)]

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids: Any) -> list:
        return []


class _Snapshotting:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, ...]] = []

    async def snapshot(self, *, run_id: UUID, candidate_ids: Any, assertions: Any) -> None:
        self.calls.append(tuple(candidate_ids))


class _RecommendationSpy:
    def __init__(self) -> None:
        self.budget_relaxed: list[bool] = []

    async def recommend(self, run_id: UUID, *, budget_relaxed: bool = False, **_: Any) -> list[Recommendation]:
        self.budget_relaxed.append(budget_relaxed)
        return []


@pytest.mark.asyncio
async def test_dat_hon_loai_cac_mau_duoi_san_truoc_khi_snapshot() -> None:
    """Xin "đắt hơn" lần hai không được trả về đúng mấy mẫu rẻ vừa bỏ qua."""

    from src.agents.core.act import act

    retrieval, snap, ranking = _Retrieval(), _Snapshotting(), _RecommendationSpy()
    services = AgentServices(
        catalog_browse=_Catalog(), retrieval=retrieval, snapshotting=snap, recommendation=ranking
    )
    state = CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, recommended_ids=(V3,),
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 300_000_000},
    )
    await act(
        Recommend(reason="revised", exclude_ids=(V3,), refine="xe khác đắt hơn"),
        state,
        services,
        run_id=RUN_ID,
        customer_id="c1",
        user_message="xe khác đắt hơn",
    )
    # VF 3 (278tr) và VF 2 (188tr) nằm DƯỚI sàn 675tr+1 → không được vào snapshot.
    assert snap.calls == [] or all(UUID(V1) not in call and UUID(V2) not in call for call in snap.calls)
    # Và bộ xếp hạng phải biết lượt này đã nới trần.
    assert ranking.budget_relaxed in ([], [True])


# ---------------------------------------------------------------- 6. MỘT bậc giá, có lời dẫn


class _StepRetrieval:
    """Catalog nhiều mẫu — đủ để thấy lượt "đắt hơn" bị đổ cả danh mục hay không."""

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        return [UUID(V1), UUID(V2), UUID(V3), UUID(V4), UUID(V5)]

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids: Any) -> list:
        return []


class _StepCatalog:
    """VF 2 188tr · VF 3 278tr · VF 5 496tr · VF 6 699tr · VF 9 1.4 tỷ."""

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        priced = (
            (V2, "VinFast VF 2", "188000000"),
            (V1, "VinFast VF 3", "278000000"),
            (V4, "VinFast VF 5", "496000000"),
            (V3, "VinFast VF 6", "699000000"),
            (V5, "VinFast VF 9", "1400000000"),
        )
        return CatalogBrowseResult(
            answer="danh mục",
            pitches=tuple(
                VehiclePitch(
                    vehicle_id=UUID(vehicle_id), rank=rank, display_name=name, pitch="",
                    starting_price_vnd=Decimal(price),
                )
                for rank, (vehicle_id, name, price) in enumerate(priced, start=1)
            ),
        )


class _StepSnapshot:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, ...]] = []

    async def snapshot(self, *, run_id: UUID, candidate_ids: Any, assertions: Any) -> None:
        self.calls.append(tuple(candidate_ids))


async def _step_turn(message: str, *, seen: tuple[str, ...]) -> tuple[Any, _StepSnapshot]:
    from src.agents.core.act import act

    snap = _StepSnapshot()
    services = AgentServices(
        catalog_browse=_StepCatalog(), retrieval=_StepRetrieval(), snapshotting=snap, recommendation=_Recommendation()
    )
    state = CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, recommended_ids=seen,
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 300_000_000},
    )
    result = await act(
        Recommend(reason="revised", exclude_ids=seen, refine=message),
        state,
        services,
        run_id=RUN_ID,
        customer_id="c1",
        user_message=message,
    )
    return result, snap


@pytest.mark.asyncio
async def test_dat_hon_chi_buoc_mot_nac_khong_do_ca_danh_muc() -> None:
    """Sếp 2026-09-23: đổ 8 thẻ một lượt là khách loạn và hết chỗ hỏi tiếp."""

    from src.agents.core.render import PRICE_STEP_LIMIT

    _, snap = await _step_turn("xe khác đắt hơn đi", seen=(V2, V1))
    assert snap.calls, "phải có snapshot của bậc vừa tìm"
    assert len(snap.calls[0]) <= PRICE_STEP_LIMIT
    # Và là các mẫu GẦN NHẤT phía trên (VF 5, VF 6, VF 9), theo giá tăng dần.
    assert snap.calls[0][0] == UUID(V4)


@pytest.mark.asyncio
async def test_re_hon_cung_chi_buoc_mot_nac() -> None:
    from src.agents.core.render import PRICE_STEP_LIMIT

    _, snap = await _step_turn("rẻ hơn được không", seen=(V3,))
    assert snap.calls and len(snap.calls[0]) <= PRICE_STEP_LIMIT


def test_cau_dan_va_loi_di_tiep_cua_bac_gia() -> None:
    from src.agents.core.render import price_step_lead, price_step_tail

    assert "cao hơn" in price_step_lead(pricier=True)
    assert "thấp hơn" in price_step_lead(pricier=False)
    # Không kết bằng dấu hai chấm: ngay sau nó là câu mở danh sách của bài.
    assert not price_step_lead(pricier=True).endswith(":")
    assert "cao hơn nữa" in price_step_tail(pricier=True, more=True)
    assert "rẻ hơn nữa" in price_step_tail(pricier=False, more=True)
    # Hết mẫu thì nói thật, không mời khách hỏi thêm một thứ không còn.
    assert "cao nhất" in price_step_tail(pricier=True, more=False)
    assert "thấp nhất" in price_step_tail(pricier=False, more=False)
