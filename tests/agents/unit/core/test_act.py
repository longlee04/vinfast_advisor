"""`act` gọi ĐÚNG một service cũ cho mỗi Action (spec mục 7).

Fake theo khuôn `tests/agents/unit/test_chain_recommendations.py`: mỗi test khai
lớp `Fake*` nhỏ rồi dựng `AgentServices(...)`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import (
    CatalogBrowseResult,
    ComparedVehicleView,
    CompareVehiclesResult,
    FilterCriteria,
    FindNearbyLocationResult,
    Recommendation,
    TcoResult,
    TestDriveResult,
    TestDriveSlotOption,
    VehicleComparisonView,
    VehicleFacts,
    VehiclePitch,
)
from src.agents.core.act import ActResult, _relax_ladder, act, build_criteria, catalog_names
from src.agents.core.actions import (
    LOOKUP_BROWSE,
    LOOKUP_LOOKUP,
    Ask,
    Book,
    Compare,
    EnqueueHitl,
    FitCheck,
    Handoff,
    Lookup,
    Nearby,
    NextSteps,
    OnRoadPrice,
    Recommend,
    Reply,
    ScopeNote,
    ShowroomOptions,
    Silent,
    Tco,
    VehicleQa,
)
from src.agents.core.state import CoreState, Pending, Stage
from src.agents.core.state import PendingKind as K
from src.agents.domain.values import SlotName as N
from src.agents.domain.values import VehicleType
from src.agents.domain.vehicle_overview import VehicleOverviewResult
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"


def _pitch(vehicle_id: str, name: str) -> VehiclePitch:
    return VehiclePitch(vehicle_id=UUID(vehicle_id), rank=1, display_name=name, pitch=f"{name} rất hợp.")


class FakeCatalogBrowse:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        self.calls.append({"user_message": user_message, "vehicle_type_hint": vehicle_type_hint})
        return CatalogBrowseResult(
            answer="Dải xe điện hiện có: VF 5, VF 6.",
            pitches=(_pitch(V1, "VinFast VF 5"), _pitch(V2, "VinFast VF 6")),
        )


class FakeCompare:
    def __init__(self) -> None:
        self.names: list[list[str]] = []

    async def answer(self, *, user_message: str, vehicle_names) -> CompareVehiclesResult:
        self.names.append(list(vehicle_names))
        return CompareVehiclesResult(answer="VF 5 rẻ hơn, VF 6 rộng hơn.", comparison=None, follow_up=None)


class FakeNearby:
    async def answer(self, **kwargs: Any) -> FindNearbyLocationResult:
        return FindNearbyLocationResult(answer="Showroom gần nhất: VinFast HTA.", locations=None)


class FakeOverview:
    def __init__(self, answer: str | None) -> None:
        self.answer_text = answer
        self.asked: list[str] = []

    async def answer(self, *, vehicle_name: str, session_id: str) -> VehicleOverviewResult:
        self.asked.append(vehicle_name)
        return VehicleOverviewResult(overview=None, answer=self.answer_text, lookup_facts=())


def _state(**kw: Any) -> CoreState:
    return CoreState(session_id="s1", **kw)


async def _act(action, state, services, **kw: Any) -> ActResult:
    return await act(
        action,
        state,
        services,
        run_id=kw.pop("run_id", None),
        customer_id="c1",
        user_message=kw.pop("user_message", ""),
    )


@pytest.mark.asyncio
async def test_lookup_browse_ep_loai_xe_tu_slot() -> None:
    browse = FakeCatalogBrowse()
    services = AgentServices(catalog_browse=browse)
    state = _state(slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Lookup(mode=LOOKUP_BROWSE), state, services, user_message="có những xe nào")
    assert result.text == "Dải xe điện hiện có: VF 5, VF 6."
    assert browse.calls == [{"user_message": "có những xe nào", "vehicle_type_hint": "CAR"}]


@pytest.mark.asyncio
async def test_lookup_lookup_khong_no_khi_service_tra_none() -> None:
    class Empty:
        async def answer(self, **_kwargs: Any) -> None:
            return None

    result = await _act(
        Lookup(mode=LOOKUP_LOOKUP), _state(), AgentServices(catalog_browse=Empty()), user_message="vf 5"
    )
    assert result.text.strip()  # không bao giờ trả lượt rỗng (chỉ số 5)


@pytest.mark.asyncio
async def test_compare_dich_id_sang_ten_xe() -> None:
    compare = FakeCompare()
    services = AgentServices(compare_vehicles=compare, catalog_browse=FakeCatalogBrowse())
    state = _state(slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Compare(vehicle_ids=(V1, V2)), state, services)
    assert compare.names == [["VinFast VF 5", "VinFast VF 6"]]
    assert "VF 5 rẻ hơn" in result.text


@pytest.mark.asyncio
async def test_nearby_goi_thang() -> None:
    result = await _act(
        Nearby(), _state(), AgentServices(nearby_location=FakeNearby()), user_message="showroom gần đây"
    )
    assert "VinFast HTA" in result.text


@pytest.mark.asyncio
async def test_vehicle_qa_co_fact() -> None:
    overview = FakeOverview("VF 5 đi được 326 km một lần sạc.")
    services = AgentServices(vehicle_overview=overview, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(VehicleQa(vehicle_id=V1, question="đi được bao xa"), state, services)
    assert overview.asked == ["VinFast VF 5"]
    assert "326 km" in result.text


@pytest.mark.asyncio
async def test_vehicle_qa_khong_co_fact_thi_de_nghi_tvv() -> None:
    overview = FakeOverview(None)
    services = AgentServices(vehicle_overview=overview, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(VehicleQa(vehicle_id=V1, question="bảo hành mấy năm"), state, services)
    assert "tư vấn viên" in result.text.lower()


@pytest.mark.asyncio
async def test_ask_choice_duoc_dien_nhan_tu_catalog() -> None:
    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Ask(key="vehicle", kind=K.CHOICE, options=(V1, V2)), state, services)
    assert "VinFast VF 5" in result.text and V1 not in result.text
    pending = result.state_patch["pending"]
    assert pending.options == (V1, V2)
    assert pending.labels == ("VinFast VF 5", "VinFast VF 6")


@pytest.mark.asyncio
async def test_ask_slot_khong_can_catalog() -> None:
    result = await _act(Ask(key="purpose", kind=K.SLOT), _state(), AgentServices())
    assert result.text.count("?") == 1
    assert result.state_patch["pending"].key == "purpose"


@pytest.mark.asyncio
async def test_reply_chosen_summary_lay_ten_xe_that() -> None:
    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Reply(template="chosen_summary", args={"vehicle_id": V1}), state, services)
    assert "VinFast VF 5" in result.text


@pytest.mark.asyncio
async def test_silent_khong_tra_chu_khong_goi_service() -> None:
    result = await _act(Silent(), _state(stage=Stage.HANDED_OFF), AgentServices())
    assert result.text == ""


@pytest.mark.asyncio
async def test_handoff_dat_chang_handed_off() -> None:
    result = await _act(Handoff(), _state(stage=Stage.RECOMMENDED), AgentServices())
    assert result.state_patch["stage"] is Stage.HANDED_OFF
    assert result.text.strip()


@pytest.mark.asyncio
async def test_catalog_names_service_hong_thi_tra_rong_khong_no() -> None:
    class Boom:
        async def answer(self, **_kwargs: Any) -> None:
            raise RuntimeError("catalog tạm thời không truy vấn được")

    assert await catalog_names(AgentServices(catalog_browse=Boom()), vehicle_type="CAR") == {}


@pytest.mark.asyncio
async def test_resume_pending_noi_cau_hoi_cu() -> None:
    from src.agents.core.state import Pending

    services = AgentServices(nearby_location=FakeNearby())
    state = _state(pending=Pending(kind=K.SLOT, key="purpose"))
    result = await _act(Nearby(resume_pending=True), state, services)
    assert "Quay lại câu lúc nãy" in result.text


# --------------------------------------------------------------- Task 2

RUN_ID = UUID("99999999-9999-9999-9999-999999999999")
CAR_FULL = {
    N.VEHICLE_TYPE: "CAR",
    N.BUDGET_MAX_VND: 900_000_000,
    N.PURPOSE: "đi làm",
    N.PASSENGER_COUNT: 5,
    N.REQUIRED_RANGE_KM: 40,
}


class FakeRetrieval:
    def __init__(self) -> None:
        self.criteria: list[FilterCriteria] = []

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        self.criteria.append(criteria)
        return [UUID(V1), UUID(V2)]

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids) -> list:
        return []


class FakeSnapshotting:
    def __init__(self) -> None:
        self.calls: list[list[UUID]] = []

    async def snapshot(self, *, run_id: UUID, candidate_ids, assertions) -> None:
        self.calls.append(list(candidate_ids))


class FakeRecommendation:
    def __init__(self) -> None:
        self.features: list[list[str]] = []

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes=(),
        preferred_trait_codes=(),
        vehicle_type=None,
        budget_relaxed: bool = False,
    ) -> list[Recommendation]:
        self.features.append(list(customer_asked_feature_codes))
        return [
            Recommendation(
                vehicle_id=UUID(V1), rank=1, reasons=["đủ 5 chỗ", "trong ngân sách"], display_name="VinFast VF 5"
            ),
            Recommendation(vehicle_id=UUID(V2), rank=2, reasons=["đi xa hơn"], display_name="VinFast VF 6"),
        ]


class RawReasonRecommendation(FakeRecommendation):
    """`reasons` ĐÚNG format thật `ScoringReason.render()` (`[slot=...] chữ`).

    `FakeRecommendation` ở trên dùng chữ tiếng Việt sạch tay viết — không bao
    giờ lộ được bug prod 2026-08-29 (đường dự phòng nối thẳng chuỗi thô của
    `ScoringReason.render()` vào câu trả khách). Fixture này chép ĐÚNG hình
    dạng chuỗi thật để test không bị lừa bởi fixture quá sạch.
    """

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes=(),
        preferred_trait_codes=(),
        vehicle_type=None,
        budget_relaxed: bool = False,
    ) -> list[Recommendation]:
        self.features.append(list(customer_asked_feature_codes))
        return [
            Recommendation(
                vehicle_id=UUID(V1),
                rank=1,
                reasons=[
                    "[slot=vehicle_type] Đúng loại phương tiện CAR đã chọn",
                    "[slot=budget_max_vnd] Giá nằm trong ngân sách đã xác nhận",
                ],
                display_name="VinFast VF 6 Plus",
            ),
        ]


class FakeSynthesis:
    def __init__(self, pitches=None, boom: bool = False) -> None:
        self.pitches = pitches
        self.boom = boom

    async def synthesize(self, **_kwargs: Any):
        if self.boom:
            # Thông điệp thật `synthesis.reject_unstructured_claims` ném trên
            # prod (2026-08-29 14:37:13) khi cả hai bộ viết đều hỏng.
            raise ValueError("suitability statement must use an approved claim placeholder")
        return self.pitches or ()


class FakeVerification:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def verify(self, *, run_id: UUID, draft_answer: str) -> bool:
        return self.ok


class FakeCandidateTuning:
    async def delegated_features(self, candidate_ids, *, vehicle_type=None, purpose=None, purpose_bucket_hint=None):
        from src.agents.services.candidate_tuning import DelegatedFeatureChoice

        return DelegatedFeatureChoice(feature_codes=("ADAS", "7_SEATER"), message="")


def _advisory_services(**overrides: Any) -> AgentServices:
    base: dict[str, Any] = {
        "retrieval": FakeRetrieval(),
        "snapshotting": FakeSnapshotting(),
        "recommendation": FakeRecommendation(),
        "synthesis": FakeSynthesis(pitches=(_pitch(V1, "VinFast VF 5"), _pitch(V2, "VinFast VF 6"))),
        "verification": FakeVerification(),
        "candidate_tuning": FakeCandidateTuning(),
        "catalog_browse": FakeCatalogBrowse(),
    }
    base.update(overrides)
    return AgentServices(**base)


def test_build_criteria_ep_loai_xe() -> None:
    criteria = build_criteria(_state(slots=CAR_FULL))
    assert criteria.vehicle_type is VehicleType.CAR
    assert criteria.budget_max_vnd == Decimal("900000000")
    assert criteria.passenger_count == 5


def test_build_criteria_thieu_loai_xe_van_co_gia_tri_hop_le() -> None:
    criteria = build_criteria(_state(slots={N.BUDGET_MAX_VND: 500_000_000}))
    assert criteria.vehicle_type is VehicleType.CAR  # mặc định, không để None lọt vào SQL


@pytest.mark.asyncio
async def test_recommend_ep_vehicle_type_va_ghi_recommended_ids() -> None:
    retrieval = FakeRetrieval()
    services = _advisory_services(retrieval=retrieval)
    state = _state(stage=Stage.COLLECTING, slots={**CAR_FULL, N.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE"})
    result = await _act(Recommend(reason="first"), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert retrieval.criteria[0].vehicle_type is VehicleType.ELECTRIC_MOTORBIKE
    assert result.state_patch["recommended_ids"] == (V1, V2)
    assert "VF 5" in result.text


class VehicleTypeCapturingRecommendation(FakeRecommendation):
    """Ghi lại đúng `vehicle_type` mà `act` truyền xuống, không tự đọc slot.

    Bug prod (15:20:30): `context.slots` (DB `conversation_slots`) chưa có
    `VEHICLE_TYPE` khi slot chỉ mới được SUY trong lượt này — service thật ném
    `ValueError` (`services/recommendation.py:234`). Fake này đứng thay service
    thật để khẳng định `act._recommend` luôn truyền tham số, không phó mặc
    service tự đọc slot rỗng.
    """

    def __init__(self) -> None:
        super().__init__()
        self.vehicle_types: list[str | None] = []

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes=(),
        preferred_trait_codes=(),
        vehicle_type=None,
        budget_relaxed: bool = False,
    ) -> list[Recommendation]:
        self.vehicle_types.append(vehicle_type)
        return await super().recommend(run_id, customer_asked_feature_codes=customer_asked_feature_codes)


@pytest.mark.asyncio
async def test_recommend_thieu_vehicle_type_ngan_sach_thap_suy_xe_may() -> None:
    recommendation = VehicleTypeCapturingRecommendation()
    services = _advisory_services(recommendation=recommendation)
    state = _state(stage=Stage.COLLECTING, slots={N.BUDGET_MAX_VND: 40_000_000, N.PURPOSE: "đi làm"})
    result = await _act(Recommend(reason="first"), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert recommendation.vehicle_types == ["ELECTRIC_MOTORBIKE"]
    assert result.state_patch["slots"][N.VEHICLE_TYPE] == "ELECTRIC_MOTORBIKE"


@pytest.mark.asyncio
async def test_recommend_thieu_vehicle_type_ngan_sach_cao_suy_o_to() -> None:
    recommendation = VehicleTypeCapturingRecommendation()
    services = _advisory_services(recommendation=recommendation)
    state = _state(stage=Stage.COLLECTING, slots={N.BUDGET_MAX_VND: 700_000_000, N.PURPOSE: "đi làm"})
    result = await _act(Recommend(reason="first"), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert recommendation.vehicle_types == ["CAR"]
    assert result.state_patch["slots"][N.VEHICLE_TYPE] == "CAR"


class BoomOnceRecommendation(FakeRecommendation):
    """`recommend` ném ĐÚNG lỗi thật trên prod — act phải bắt, không được nổ."""

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes=(),
        preferred_trait_codes=(),
        vehicle_type=None,
        budget_relaxed: bool = False,
    ) -> list[Recommendation]:
        raise ValueError("vehicle_type slot is required and must be valid")


@pytest.mark.asyncio
async def test_recommend_service_loi_van_tra_loi_sach_khong_no_luot() -> None:
    services = _advisory_services(recommendation=BoomOnceRecommendation())
    state = _state(stage=Stage.COLLECTING, slots={N.BUDGET_MAX_VND: 500_000_000, N.PURPOSE: "đi làm"})
    result = await _act(Recommend(reason="first"), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert result.text.strip()
    assert "ô tô" in result.text and "xe máy" in result.text
    assert result.state_patch["pending"].key == "vehicle_type"


@pytest.mark.asyncio
async def test_recommend_retry_loai_xe_da_de_xuat() -> None:
    retrieval = FakeRetrieval()
    snapshotting = FakeSnapshotting()
    services = _advisory_services(retrieval=retrieval, snapshotting=snapshotting)
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1,), slots=CAR_FULL)
    await _act(Recommend(reason="retry", exclude_ids=(V1,)), state, services, run_id=RUN_ID, user_message="mẫu khác đi")
    assert snapshotting.calls == [[UUID(V2)]]


@pytest.mark.asyncio
async def test_recommend_synthesis_hong_thi_du_phong_co_ten_va_ly_do() -> None:
    services = _advisory_services(synthesis=FakeSynthesis(boom=True))
    result = await _act(Recommend(), _state(slots=CAR_FULL), services, run_id=RUN_ID, user_message="tư vấn")
    assert "VinFast VF 5" in result.text
    assert "đủ 5 chỗ" in result.text
    assert "Em có thể đặt lịch lái thử" not in result.text  # không boilerplate


@pytest.mark.asyncio
async def test_recommend_synthesis_hong_reason_tho_van_ra_cau_sach_khong_bao_loi() -> None:
    """Bug prod 2026-08-29: `synthesis` ném `ValueError` ("suitability statement
    must use an approved claim placeholder"), đường dự phòng nối THẲNG
    `Recommendation.reasons` thô (`[slot=vehicle_type] ...`) vào câu trả khách,
    `assert_clean` chặn token `vehicle_type`, `RenderError` bắn lên `act` và cả
    lượt rơi về câu an toàn ("act hong"). `act` không được ném lỗi, và câu trả
    ra phải sạch — không còn dấu vết `[slot=...]`/mã máy nào.
    """

    services = _advisory_services(synthesis=FakeSynthesis(boom=True), recommendation=RawReasonRecommendation())
    result = await _act(Recommend(), _state(slots=CAR_FULL), services, run_id=RUN_ID, user_message="tư vấn")
    assert "VinFast VF 6 Plus" in result.text
    assert "[slot=" not in result.text
    assert "vehicle_type" not in result.text
    assert "budget_max_vnd" not in result.text


@pytest.mark.asyncio
async def test_recommend_du_phong_van_dinh_chu_cam_thi_roi_bac_cuoi_khong_bao_loi() -> None:
    """Lưới an toàn CUỐI (defensive): `needs` là chữ khách tự gõ, KHÔNG qua lọc
    reason/claim của bước 1 — khách gõ nguyên một mã kiểu máy (gạch dưới, chữ
    thường) vẫn có thể làm `recommend_fallback` bị `assert_clean` chặn. `act`
    KHÔNG được ném lỗi: phải rơi về dòng tối giản "<xe> — giá <...>".
    """

    services = _advisory_services(synthesis=FakeSynthesis(boom=True))
    state = _state(slots={**CAR_FULL, N.PURPOSE: "gia_dinh_dong_con"})
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="tư vấn")
    assert "VinFast VF 5" in result.text
    assert "giá" in result.text
    assert "gia_dinh_dong_con" not in result.text
    assert "[slot=" not in result.text


@pytest.mark.asyncio
async def test_recommend_verify_truot_cung_ra_du_phong() -> None:
    services = _advisory_services(verification=FakeVerification(ok=False))
    result = await _act(Recommend(), _state(slots=CAR_FULL), services, run_id=RUN_ID, user_message="tư vấn")
    assert "VinFast VF 5" in result.text and "rất hợp" not in result.text


@pytest.mark.asyncio
async def test_recommend_dien_option_cho_pending_feature() -> None:
    from src.agents.core.state import Pending

    services = _advisory_services()
    state = _state(slots=CAR_FULL, pending=Pending(kind=K.SLOT, key="habit_need_tags"))
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="tư vấn")
    pending = result.state_patch["pending"]
    # Mã nào không bảng nào dịch được thì bị LOẠI cả mã lẫn nhãn — nên chỉ khẳng
    # định "có option, song song với nhãn, và không mã thô nào lọt ra".
    assert pending.options and set(pending.options) <= {"ADAS", "7_SEATER"}
    assert len(pending.labels) == len(pending.options)
    assert all(label not in {"ADAS", "7_SEATER"} for label in pending.labels)


@pytest.mark.asyncio
async def test_tco_truyen_region_tu_slot() -> None:
    seen: dict[str, Any] = {}

    class FakeTco:
        async def estimate(
            self, *, vehicle_id, daily_distance_km, run_id=None, region_code=None, discount_vnd=Decimal("0")
        ):
            seen.update(vehicle_id=vehicle_id, daily=daily_distance_km, region=region_code)
            return TcoResult(
                vehicle_id=vehicle_id,
                total_vnd=Decimal("180000000"),
                components_vnd={"energy": Decimal("60000000")},
                assumptions_id=None,
                computed_at=datetime.now(UTC),
            )

    services = AgentServices(tco_estimation=FakeTco(), catalog_browse=FakeCatalogBrowse())
    # Bước 2 (`validate_slots`) ghi CHỮ TỰ DO vào slot ("Hà Nội"), không phải mã
    # tỉnh. Đưa thẳng chữ đó cho `region_for_province_code` là rơi về KHU_VUC_II
    # — sai khu vực phí cho đúng hai tỉnh đông khách nhất (finding I3).
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "Hà Nội"})
    result = await _act(Tco(vehicle_id=V1), state, services, run_id=RUN_ID)
    assert seen["region"] == "KHU_VUC_I"
    assert seen["daily"] == 40
    assert result.text.strip()


@pytest.mark.asyncio
async def test_tco_khong_co_du_lieu_thi_noi_that() -> None:
    class FakeTco:
        async def estimate(self, **_kwargs: Any) -> TcoResult:
            return TcoResult(
                vehicle_id=UUID(V1),
                total_vnd=None,
                components_vnd={},
                assumptions_id=None,
                computed_at=datetime.now(UTC),
                unavailable_reason="TCO_UNAVAILABLE",
            )

    services = AgentServices(tco_estimation=FakeTco(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(Tco(vehicle_id=V1), state, services, run_id=RUN_ID)
    assert "tư vấn viên" in result.text.lower()
    assert "TCO_UNAVAILABLE" not in result.text


class FakeTcoForOnRoad:
    """Cửa `tco_estimation` mà lượt GIÁ LĂN BÁNH giờ phải gọi (Sếp 2026-08-31:
    "giá lăn bánh với TCO là MỘT" — lượt này trả đúng thẻ chi phí, không còn đi
    đường chữ `on_road_price`). Ghi lại region/daily để test soi khu vực phí."""

    def __init__(self) -> None:
        self.seen: dict[str, Any] = {}

    async def estimate(self, *, vehicle_id, daily_distance_km, run_id=None, region_code=None):
        self.seen.update(vehicle_id=vehicle_id, daily=daily_distance_km, region=region_code)
        return TcoResult(
            vehicle_id=vehicle_id,
            total_vnd=Decimal("560000000"),
            components_vnd={
                "promoted_purchase_price_vnd": Decimal("480000000"),
                "rolling_fees_vnd": Decimal("30000000"),
                "energy_vnd": Decimal("50000000"),
            },
            assumptions_id=None,
            computed_at=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_gia_lan_banh_tra_the_chi_phi_suy_khu_vuc_tu_slot() -> None:
    """Thiết kế 2026-08-31: lượt giá lăn bánh trả THẺ chi phí — tỉnh trong slot
    prefill vào ô chọn của thẻ và quyết định khu vực phí, không hỏi lại."""

    service = FakeTcoForOnRoad()
    services = AgentServices(tco_estimation=service, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    result = await _act(OnRoadPrice(vehicle_id=V1), state, services, user_message="giá lăn bánh bao nhiêu")
    assert service.seen["region"] == "KHU_VUC_I"
    card = result.cards["tco_card"]
    assert card.vehicle_name == "VinFast VF 5"
    assert card.province_code == "HN"
    assert "lăn bánh" in result.text  # câu dẫn trỏ vào thẻ, không đọc số trong chat
    assert "pending" not in result.state_patch


@pytest.mark.asyncio
async def test_gia_lan_banh_chua_biet_tinh_mac_dinh_khu_vuc_2_khong_hoi() -> None:
    """ĐẢO kỳ vọng cũ (LP35 từng bắt HỎI tỉnh khi không suy ra được) theo thiết
    kế 2026-08-31: thẻ có ô chọn tỉnh ngay trên bảng nên KHÔNG hỏi nữa — tính
    theo mặc định Khu vực II đúng như thẻ chi phí vẫn làm, ô tỉnh để TRỐNG cho
    khách tự chọn. Không còn là "con số bịa cho An Giang": thẻ không điền tỉnh
    nào, và `assumption_note` nói rõ đang tính theo khu vực nào."""

    service = FakeTcoForOnRoad()
    services = AgentServices(
        tco_estimation=service, catalog_browse=FakeCatalogBrowse(), conversation=FakeConversationLocation(None)
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL, turn_count=3)
    result = await _act(OnRoadPrice(vehicle_id=V1), state, services, user_message="tính giá lăn bánh")
    assert service.seen["region"] == "KHU_VUC_II"
    card = result.cards["tco_card"]
    assert card.province_code is None  # không bịa tỉnh — khách chọn trên thẻ
    assert "An Giang" not in result.text
    assert "pending" not in result.state_patch  # không treo câu hỏi tỉnh nữa
    assert "tỉnh" in result.text  # câu dẫn chỉ chỗ chọn tỉnh ngay trên bảng


@pytest.mark.asyncio
async def test_gia_lan_banh_lay_tinh_tu_vi_tri_da_luu_thay_vi_mac_dinh() -> None:
    """Khách đã chia sẻ vị trí ở trang bản đồ: tỉnh đó prefill vào thẻ luôn."""

    service = FakeTcoForOnRoad()
    services = AgentServices(
        tco_estimation=service, catalog_browse=FakeCatalogBrowse(), conversation=FakeConversationLocation(_HANOI)
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(OnRoadPrice(vehicle_id=V1), state, services, user_message="tính giá lăn bánh")
    assert service.seen["region"] == "KHU_VUC_I"
    assert result.cards["tco_card"].province_code == "HN"
    assert "pending" not in result.state_patch


@pytest.mark.asyncio
async def test_tco_refreshed_noi_da_cap_nhat_khong_doc_bai_dan_moi() -> None:
    """Khách nhắc lại km/tỉnh SAU khi thẻ đã hiện (policy 5a' bắn cờ refreshed):
    chữ phải xác nhận ĐÃ cập nhật thẻ cũ — client thay số tại chỗ, không thẻ mới."""

    services = AgentServices(tco_estimation=FakeTcoForOnRoad(), catalog_browse=FakeCatalogBrowse())
    state = _state(
        stage=Stage.COSTING,
        chosen_vehicle_id=V1,
        slots={**CAR_FULL, N.REQUIRED_RANGE_KM: 60, N.REGISTRATION_PROVINCE: "Đà Nẵng"},
    )
    result = await _act(Tco(vehicle_id=V1, refreshed_km=True, refreshed_province=True), state, services, run_id=RUN_ID)
    assert "cập nhật" in result.text
    assert "60 km" in result.text and "Đà Nẵng" in result.text
    card = result.cards["tco_card"]
    assert card.province_code == "DN" and card.daily_distance_km == 60.0


class FakeTestDriveAnswer:
    """Chữ ký ĐÚNG như `TestDriveServiceImpl.answer` (services/test_drive.py:202).

    Protocol trong `registry.py` thiếu `session_id`/`customer_id`; fake bám bản
    thật, nếu không test xanh mà prod ném `TypeError` ngay lượt lái thử đầu tiên.
    """

    def __init__(self, slot_options: tuple[TestDriveSlotOption, ...] = ()) -> None:
        self.seen: dict[str, Any] = {}
        self.slot_options = slot_options

    async def answer(
        self, *, user_message, vehicle_name, vehicle_type, known_location, session_id, customer_id
    ) -> TestDriveResult:
        self.seen.update(
            user_message=user_message,
            vehicle_name=vehicle_name,
            vehicle_type=vehicle_type,
            known_location=known_location,
            session_id=session_id,
            customer_id=customer_id,
        )
        if known_location is None:
            return TestDriveResult(answer="Anh/chị đang ở khu vực nào ạ?", needs_location=True)
        return TestDriveResult(
            answer="Showroom gần anh/chị: VinFast HTA, còn khung 9:00.",
            card=None,
            slot_options=self.slot_options,
        )


class FakeConversationLocation:
    """Chỉ có `load_user_location` — đúng cửa mà `chain._load_user_location` dùng."""

    def __init__(self, payload: dict[str, Any] | None) -> None:
        self.payload = payload
        self.asked: list[str] = []

    async def load_user_location(self, session_id: str) -> dict[str, Any] | None:
        self.asked.append(session_id)
        return self.payload


_HANOI = {"latitude": 21.0278, "longitude": 105.8342, "source": "browser", "label": "Hà Nội"}


@pytest.mark.asyncio
async def test_showroom_options_truyen_du_chu_ky_that_va_vi_tri_da_biet() -> None:
    conversation = FakeConversationLocation(_HANOI)
    test_drive = FakeTestDriveAnswer()
    services = AgentServices(test_drive=test_drive, catalog_browse=FakeCatalogBrowse(), conversation=conversation)
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lái thử")
    assert test_drive.seen["vehicle_type"] is VehicleType.CAR
    assert test_drive.seen["session_id"] == "s1"
    assert test_drive.seen["customer_id"] == "c1"
    assert conversation.asked == ["s1"]
    # Vị trí đã biết → service ra được showroom, KHÔNG rơi vào nhánh hỏi vị trí.
    assert test_drive.seen["known_location"] is not None
    assert "VinFast HTA" in result.text


@pytest.mark.asyncio
async def test_showroom_options_slot_options_thanh_nut_quick_replies() -> None:
    when = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
    options = (
        TestDriveSlotOption(
            showroom="VinFast HTA", scheduled_at=when, label="9:00 30/08 — VinFast HTA", value="__lichlaithu__|a|b"
        ),
    )
    test_drive = FakeTestDriveAnswer(slot_options=options)
    services = AgentServices(
        test_drive=test_drive, catalog_browse=FakeCatalogBrowse(), conversation=FakeConversationLocation(_HANOI)
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lái thử")
    replies = result.cards["quick_replies"]
    assert [(reply.label, reply.value) for reply in replies] == [("9:00 30/08 — VinFast HTA", "__lichlaithu__|a|b")]


@pytest.mark.asyncio
async def test_showroom_options_chua_biet_vi_tri_thi_hoi_khong_no() -> None:
    test_drive = FakeTestDriveAnswer()
    services = AgentServices(
        test_drive=test_drive, catalog_browse=FakeCatalogBrowse(), conversation=FakeConversationLocation(None)
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lái thử")
    # Slot tỉnh "Hà Nội"/"HN" không có trong CAR_FULL và phiên chưa lưu vị trí:
    # `act` trả thẻ xin vị trí, KHÔNG gọi `test_drive.answer` chỉ để nhận lại câu hỏi đó.
    assert test_drive.seen == {}
    assert result.text.strip()
    assert not result.cards.get("quick_replies")
    assert result.cards["test_drive_card"].needs_location is True


@pytest.mark.asyncio
async def test_book_doc_nut_qua_read_slot_token_khong_split(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agents.core.act as act_module
    from src.agents.domain.test_drive_booking import BookingChoice

    when = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
    monkeypatch.setattr(
        act_module,
        "read_slot_token",
        lambda message, **_kwargs: BookingChoice(showroom="VinFast HTA", scheduled_at=when),
    )

    booked: dict[str, Any] = {}

    class FakeTestDrive:
        async def book(self, *, customer_id, vehicle_id, showroom, scheduled_at):
            booked.update(customer_id=customer_id, vehicle_id=vehicle_id, showroom=showroom, at=scheduled_at)
            return uuid4()

    services = AgentServices(test_drive=FakeTestDrive(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(
        Book(vehicle_id=V1, choice_ref="__lichlaithu__|abc|def"), state, services, user_message="__lichlaithu__|abc|def"
    )
    assert booked["showroom"] == "VinFast HTA" and booked["at"] == when
    assert "VinFast HTA" in result.text and "__" not in result.text
    assert result.state_patch["stage"] is Stage.CHOSEN


@pytest.mark.asyncio
async def test_book_nut_hong_thi_hoi_lai_khong_dat_bua(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agents.core.act as act_module

    monkeypatch.setattr(act_module, "read_slot_token", lambda message, **_kwargs: None)

    class NeverBook:
        async def book(self, **_kwargs: Any):
            raise AssertionError("không được đặt lịch từ mã hỏng")

    services = AgentServices(test_drive=NeverBook(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(Book(vehicle_id=V1, choice_ref="rác"), state, services, user_message="rác")
    assert result.state_patch.get("stage") is not Stage.CHOSEN or "chọn lại" in result.text.lower()


@pytest.mark.asyncio
async def test_enqueue_hitl_tra_ve_request_khong_tu_ghi() -> None:
    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.OFFER_REVIEW, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(
        EnqueueHitl(vehicle_id=V1), state, services, run_id=RUN_ID, user_message="có khuyến mãi gì không"
    )
    assert result.hitl_request is not None
    assert result.hitl_request.run_id == RUN_ID
    assert "VinFast VF 5" in result.hitl_request.content
    assert result.state_patch["stage"] is Stage.OFFER_REVIEW


# --------------------------------------------------------------- đợt sửa cuối


@pytest.mark.asyncio
async def test_ask_confirm_offer_duoc_dien_nhan_khong_doc_uuid() -> None:
    """`policy._guard(key=CONFIRM_OFFER, treo=vehicle_id)` treo id thô (policy.py:228).

    `_ask` chỉ điền nhãn cho CHOICE nên câu xác nhận từng đọc nguyên uuid.
    """

    from src.agents.core.actions import CONFIRM_OFFER

    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.OFFER_REVIEW, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Ask(key=CONFIRM_OFFER, kind=K.CONFIRM, options=(V1,)), state, services)
    assert V1 not in result.text
    assert "VinFast VF 5" in result.text
    assert result.state_patch["pending"].labels and V1 not in result.state_patch["pending"].labels[0]


@pytest.mark.asyncio
async def test_ask_confirm_offer_ten_tra_khong_ra_van_khong_lo_id() -> None:
    from src.agents.core.actions import CONFIRM_OFFER

    class EmptyCatalog:
        async def answer(self, **_kwargs: Any) -> None:
            return None

    state = _state(stage=Stage.OFFER_REVIEW, chosen_vehicle_id=V1)
    result = await _act(
        Ask(key=CONFIRM_OFFER, kind=K.CONFIRM, options=(V1,)), state, AgentServices(catalog_browse=EmptyCatalog())
    )
    assert V1 not in result.text and result.text.strip()


@pytest.mark.asyncio
async def test_tco_slot_da_la_ma_tinh_thi_giu_nguyen() -> None:
    seen: dict[str, Any] = {}

    class FakeTco:
        async def estimate(
            self, *, vehicle_id, daily_distance_km, run_id=None, region_code=None, discount_vnd=Decimal("0")
        ):
            seen["region"] = region_code
            return TcoResult(
                vehicle_id=vehicle_id,
                total_vnd=Decimal("180000000"),
                components_vnd={},
                assumptions_id=None,
                computed_at=datetime.now(UTC),
            )

    services = AgentServices(tco_estimation=FakeTco(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HCM"})
    await _act(Tco(vehicle_id=V1), state, services, run_id=RUN_ID)
    assert seen["region"] == "KHU_VUC_I"


@pytest.mark.asyncio
async def test_tco_slot_tinh_ngoai_khu_vuc_mot() -> None:
    seen: dict[str, Any] = {}

    class FakeTco:
        async def estimate(
            self, *, vehicle_id, daily_distance_km, run_id=None, region_code=None, discount_vnd=Decimal("0")
        ):
            seen["region"] = region_code
            return TcoResult(
                vehicle_id=vehicle_id,
                total_vnd=Decimal("180000000"),
                components_vnd={},
                assumptions_id=None,
                computed_at=datetime.now(UTC),
            )

    services = AgentServices(tco_estimation=FakeTco(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "Đà Nẵng"})
    await _act(Tco(vehicle_id=V1), state, services, run_id=RUN_ID)
    assert seen["region"] == "KHU_VUC_II"


# --------------------------------------------------------------- answer "bẩn"

#: `answer` của service cũ được MIỄN `assert_clean` (global constraints): dấu
#: `[1]` là bản đối chiếu hợp lệ, `260.00`/`lfp_battery` đến từ dữ liệu cũ. Bắt
#: chúng ở lõi v2 là giết lượt của khách vì chữ của tầng khác.
DIRTY = "VF 5 có cốp 260.00 lít, pin lfp_battery, tầm chạy 326 km [1]."


class DirtyCatalogBrowse(FakeCatalogBrowse):
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        await super().answer(user_message=user_message, vehicle_type_hint=vehicle_type_hint)
        return CatalogBrowseResult(answer=DIRTY, pitches=(_pitch(V1, "VinFast VF 5"), _pitch(V2, "VinFast VF 6")))


@pytest.mark.asyncio
async def test_lookup_answer_ban_di_thang_khong_bi_chan() -> None:
    result = await _act(
        Lookup(mode=LOOKUP_BROWSE), _state(), AgentServices(catalog_browse=DirtyCatalogBrowse()), user_message="xe nào"
    )
    assert result.text == DIRTY


@pytest.mark.asyncio
async def test_vehicle_qa_answer_ban_di_thang_khong_bi_chan() -> None:
    services = AgentServices(vehicle_overview=FakeOverview(DIRTY), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(VehicleQa(vehicle_id=V1, question="cốp bao nhiêu"), state, services)
    # Đợt 9: bảng tổng quan giữ NGUYÊN chữ service cũ, chỉ nối câu kết theo checklist phía sau.
    assert result.text.startswith(DIRTY)
    assert result.text.endswith(
        "Để rõ tổng tiền trước khi quyết: anh/chị muốn xem chi phí 5 năm, giá lăn bánh, hay đặt lái thử VinFast VF 5?"
    )


@pytest.mark.asyncio
async def test_compare_answer_ban_di_thang_khong_bi_chan() -> None:
    class DirtyCompare:
        async def answer(self, *, user_message: str, vehicle_names) -> CompareVehiclesResult:
            return CompareVehiclesResult(answer=DIRTY, comparison=None, follow_up=None)

    services = AgentServices(compare_vehicles=DirtyCompare(), catalog_browse=FakeCatalogBrowse())
    state = _state(slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Compare(vehicle_ids=(V1, V2)), state, services)
    assert result.text == DIRTY


@pytest.mark.parametrize("action_name", ["lookup", "vehicle_qa", "compare"])
@pytest.mark.asyncio
async def test_answer_ban_van_noi_duoc_cau_hoi_treo(action_name: str) -> None:
    """Nhánh chen ngang: `answer` bẩn + pending treo phải ra ĐỦ hai phần.

    Trước đây `render_resume` soi cả `main` → `RenderError` → khách mất cả câu
    trả lời lẫn câu hỏi (chỉ số 2 spec mục 8).
    """

    from src.agents.core.state import Pending

    class DirtyCompare:
        async def answer(self, *, user_message: str, vehicle_names) -> CompareVehiclesResult:
            return CompareVehiclesResult(answer=DIRTY, comparison=None, follow_up=None)

    services = AgentServices(
        catalog_browse=DirtyCatalogBrowse(),
        vehicle_overview=FakeOverview(DIRTY),
        compare_vehicles=DirtyCompare(),
    )
    state = _state(
        stage=Stage.CHOSEN,
        chosen_vehicle_id=V1,
        slots={N.VEHICLE_TYPE: "CAR"},
        pending=Pending(kind=K.SLOT, key="purpose"),
    )
    actions = {
        "lookup": Lookup(mode=LOOKUP_BROWSE, resume_pending=True),
        "vehicle_qa": VehicleQa(vehicle_id=V1, question="cốp bao nhiêu", resume_pending=True),
        "compare": Compare(vehicle_ids=(V1, V2), resume_pending=True),
    }
    result = await _act(actions[action_name], state, services, user_message="hỏi thêm")
    assert result.text.startswith(DIRTY)
    assert "Quay lại câu lúc nãy" in result.text


# ---------- bước 4: giá lăn bánh gọi đúng cửa `answer_with_pending` ----------


class NeverOnRoadService:
    """Đường CHỮ cũ của giá lăn bánh — thiết kế 2026-08-31 cấm act gọi vào.

    Thẻ chi phí là nguồn số duy nhất; còn một đường chữ chạy song song là hai
    con số cho cùng một câu hỏi trên cùng một màn hình. Fake này nổ to nếu act
    còn rẽ vào bất kỳ cửa nào của service cũ.
    """

    async def answer_with_pending(self, **_kwargs: Any):  # pragma: no cover - phải không bao giờ chạy
        raise AssertionError("act không được đi đường chữ on_road_price nữa — lăn bánh trả thẻ chi phí")

    async def answer(self, **_kwargs: Any):  # pragma: no cover - phải không bao giờ chạy
        raise AssertionError("đường chết answer() — không bao giờ được gọi")


@pytest.mark.asyncio
async def test_gia_lan_banh_khong_goi_service_chu_va_the_mang_nhom() -> None:
    service = FakeTcoForOnRoad()
    services = AgentServices(
        tco_estimation=service, on_road_price=NeverOnRoadService(), catalog_browse=FakeCatalogBrowse()
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    result = await _act(OnRoadPrice(vehicle_id=V1), state, services, user_message="tính giá lăn bánh")
    # Các khoản phải mang nhóm để client tách "Chi phí lăn bánh ban đầu" ra
    # nhóm đầu bảng — đúng chỗ câu dẫn đang trỏ khách nhìn vào.
    groups = {item.code: item.group for item in result.cards["tco_card"].components}
    assert groups["promoted_purchase_price_vnd"] == "rolling"
    assert groups["rolling_fees_vnd"] == "rolling"
    assert groups["energy_vnd"] == "operating"


@pytest.mark.asyncio
async def test_gia_lan_banh_khong_co_du_lieu_thi_noi_that() -> None:
    class Unavailable:
        async def estimate(self, **_kwargs: Any):
            return TcoResult(
                vehicle_id=UUID(V1),
                total_vnd=None,
                components_vnd={},
                assumptions_id=None,
                computed_at=datetime.now(UTC),
                unavailable_reason="TCO_UNAVAILABLE",
            )

    services = AgentServices(tco_estimation=Unavailable(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    result = await _act(OnRoadPrice(vehicle_id=V1), state, services, user_message="tính giá lăn bánh")
    assert "tư vấn viên" in result.text.lower()
    assert "TCO_UNAVAILABLE" not in result.text


# ---------- bước 4: đề xuất lại KHÔNG đọc lại nguyên bài cũ ----------


@pytest.mark.asyncio
async def test_recommend_retry_het_xe_moi_thi_noi_van_thay_xe_cu_hop_nhat() -> None:
    """Loại hết xe đã đề xuất mà không còn ứng viên nào: KHÔNG được nói "chưa
    tìm được mẫu nào khớp" (sai — vừa tìm ra ba mẫu xong), cũng không đọc lại
    nguyên bài. Một câu ngắn xác nhận lựa chọn cũ rồi mở đường đi tiếp."""

    services = _advisory_services()
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="retry", exclude_ids=(V1, V2)),
        state,
        services,
        run_id=RUN_ID,
        user_message="thôi không cần tính năng gì",
    )
    assert "VinFast VF 5" in result.text
    assert "rất hợp." not in result.text  # không phải bài pitch của synthesis
    assert "chưa tìm được" not in result.text.lower()
    assert result.text.count("?") == 1


@pytest.mark.asyncio
async def test_recommend_ra_dung_bo_xe_cu_thi_khong_doc_lai_bai() -> None:
    """Cùng bộ xe → cùng bài chữ. Đọc lại nguyên văn là chỉ số "lặp bài"."""

    services = _advisory_services()
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="slots_changed"), state, services, run_id=RUN_ID, user_message="thế còn mẫu nào"
    )
    assert "rất hợp." not in result.text
    assert "vẫn thấy" in result.text
    assert result.state_patch["recommended_ids"] == (V1, V2)


@pytest.mark.asyncio
async def test_recommend_lan_dau_khong_co_xe_nao_van_noi_that() -> None:
    """Chưa từng đề xuất mà lọc ra rỗng thì câu "chưa tìm được mẫu nào" MỚI đúng."""

    class Empty:
        async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
            return []

        async def layer2(self, **_kwargs: Any) -> list:
            return []

    services = _advisory_services(retrieval=Empty())
    result = await _act(
        Recommend(reason="first"), _state(slots=CAR_FULL), services, run_id=RUN_ID, user_message="tư vấn"
    )
    assert "chưa tìm được" in result.text.lower()


# ---------- bước 4 (Sếp chốt 2026-08-29): thiếu slot thì SUY, không hỏi thêm ----------


def test_suy_loai_xe_tu_ngan_sach_nho_la_xe_may() -> None:
    from src.agents.core.act import infer_vehicle_type

    state = _state(slots={N.BUDGET_MAX_VND: 40_000_000, N.REQUIRED_RANGE_KM: 30})
    assert infer_vehicle_type(state) is VehicleType.ELECTRIC_MOTORBIKE
    assert build_criteria(state).vehicle_type is VehicleType.ELECTRIC_MOTORBIKE


def test_suy_loai_xe_tu_ngan_sach_lon_la_o_to() -> None:
    from src.agents.core.act import infer_vehicle_type

    assert infer_vehicle_type(_state(slots={N.BUDGET_MAX_VND: 900_000_000})) is VehicleType.CAR


def test_khach_noi_loai_xe_thi_khong_suy_theo_tien() -> None:
    from src.agents.core.act import infer_vehicle_type

    state = _state(slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 40_000_000})
    assert infer_vehicle_type(state) is VehicleType.CAR


@pytest.mark.asyncio
async def test_tco_thieu_km_thi_tam_tinh_va_noi_ro_muc_tam_tinh() -> None:
    from src.agents.core.act import DEFAULT_DAILY_KM

    seen: dict[str, Any] = {}

    class FakeTco:
        async def estimate(
            self, *, vehicle_id, daily_distance_km, run_id=None, region_code=None, discount_vnd=Decimal("0")
        ):
            seen["daily"] = daily_distance_km
            return TcoResult(
                vehicle_id=vehicle_id,
                total_vnd=Decimal("180000000"),
                components_vnd={},
                assumptions_id=None,
                computed_at=datetime.now(UTC),
            )

    services = AgentServices(tco_estimation=FakeTco(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Tco(vehicle_id=V1), state, services, run_id=RUN_ID)
    assert seen["daily"] == float(DEFAULT_DAILY_KM)
    # Sếp 2026-08-31: chữ KHÔNG giả định km nữa — thẻ là nơi khách tự chỉnh.
    assert "chỉnh khu vực và số km" in result.text
    assert "tạm tính" not in result.text


# ---------- bước 5: bài đề xuất diễn giải tính năng THEO NHU CẦU ----------


@pytest.mark.asyncio
async def test_recommend_gui_nhu_cau_khach_sang_synthesis() -> None:
    """Thiếu `customer_wording` thì bài viết ra đúng số nhưng không dính gì tới
    việc khách vừa kể — đúng khối mà `nodes/synthesize` vẫn gửi."""

    seen: dict[str, Any] = {}

    class SpySynthesis(FakeSynthesis):
        async def synthesize(self, **kwargs: Any):
            seen.update(kwargs)
            return self.pitches or ()

    services = _advisory_services(synthesis=SpySynthesis(pitches=(_pitch(V1, "VinFast VF 5"),)))
    state = _state(slots={**CAR_FULL, N.PURPOSE: "đưa đón con", N.HABIT_NEED_TAGS: ["7_SEATER"]})
    await _act(Recommend(reason="first"), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert "đưa đón con" in seen["customer_wording"]
    assert seen["feature_mention_codes"] == ["7_SEATER"]
    # Mã tính năng vào prompt phải là NHÃN tiếng Việt, không phải mã thô.
    assert "7_SEATER" not in seen["customer_wording"]
    assert any("chỗ" in item for item in seen["customer_wording"])


@pytest.mark.asyncio
async def test_du_phong_noi_ro_theo_nhu_cau_nao() -> None:
    services = _advisory_services(synthesis=FakeSynthesis(boom=True))
    state = _state(slots={**CAR_FULL, N.PURPOSE: "chạy grab"})
    result = await _act(Recommend(reason="first"), state, services, run_id=RUN_ID, user_message="tư vấn")
    assert "chạy grab" in result.text
    assert "VinFast VF 5" in result.text
    # MỖI xe một câu nối tính năng/lý do với chính việc khách vừa kể — không chỉ
    # một dòng mở đầu chung chung.
    assert "hợp với chạy grab nhờ" in result.text


# ---------- bước 8: thẻ showroom và nút khung giờ phải thật sự đi ra ----------


def _slot_token(showroom: str, when: datetime) -> str:
    from src.agents.services.slot_token import issue_slot_token

    return issue_slot_token(
        showroom=showroom,
        scheduled_at=when,
        session_id="s1",
        customer_id="c1",
        issued_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_showroom_doi_ten_tinh_ra_toa_do_de_co_nut_khung_gio() -> None:
    """Lỗi prod: lõi v2 chỉ ghi TỈNH vào slot, không ai đổi ra toạ độ, nên
    `test_drive.answer` luôn thấy `known_location=None` → không thẻ, không nút,
    và đường `__lichlaithu__` không bao giờ chạm tới được."""

    from src.agents.domain.nearby_location import UserLocation

    when = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    option = TestDriveSlotOption(
        showroom="VinFast HTA",
        scheduled_at=when,
        label="VinFast HTA - 09:00 ngày 01/09",
        value=_slot_token("VinFast HTA", when),
    )

    class FakeNearbyResolve:
        def __init__(self) -> None:
            self.seen: dict[str, Any] = {}

        async def answer(self, **kwargs: Any) -> FindNearbyLocationResult:
            self.seen.update(kwargs)
            return FindNearbyLocationResult(
                answer="Showroom gần Hà Nội.",
                locations=None,
                resolved_location=UserLocation(latitude=21.0, longitude=105.8),
            )

    nearby = FakeNearbyResolve()
    drive = FakeTestDriveAnswer(slot_options=(option,))
    services = AgentServices(test_drive=drive, nearby_location=nearby, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "Hà Nội"})
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lịch lái thử")
    assert nearby.seen["location_text"] == "Hà Nội"
    assert drive.seen["known_location"] is not None
    values = [reply.value for reply in result.cards["quick_replies"]]
    assert values and all(value.startswith("__lichlaithu__|") for value in values)


@pytest.mark.asyncio
async def test_showroom_khong_co_tinh_thi_van_hoi_vi_tri_khong_no() -> None:
    drive = FakeTestDriveAnswer()
    services = AgentServices(test_drive=drive, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lịch lái thử")
    assert drive.seen == {}
    assert result.text.strip()


# ---------- bước 12: vòng tinh chỉnh đề xuất theo lời khách ----------


class SpyRecommendation(FakeRecommendation):
    """Ghi lại đúng bộ tham số chấm điểm mà `act` truyền xuống."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: dict[str, Any] = {}

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes=(),
        preferred_trait_codes=(),
        vehicle_type=None,
        budget_relaxed: bool = False,
    ) -> list[Recommendation]:
        self.seen.update(features=list(customer_asked_feature_codes), traits=list(preferred_trait_codes))
        return await super().recommend(run_id, customer_asked_feature_codes=customer_asked_feature_codes)


class PricedCatalog(FakeCatalogBrowse):
    """Catalog có GIÁ — cần cho lượt "rẻ hơn" (trần mới đọc từ giá đã xem)."""

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="Dải xe điện hiện có: VF 5, VF 6.",
            pitches=(
                VehiclePitch(
                    vehicle_id=UUID(V1),
                    rank=1,
                    display_name="VinFast VF 5",
                    pitch="x",
                    starting_price_vnd=Decimal("500000000"),
                ),
                VehiclePitch(
                    vehicle_id=UUID(V2),
                    rank=2,
                    display_name="VinFast VF 6",
                    pitch="y",
                    starting_price_vnd=Decimal("800000000"),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_xin_re_hon_thi_ha_tran_ngan_sach_duoi_gia_da_xem() -> None:
    retrieval = FakeRetrieval()
    services = _advisory_services(retrieval=retrieval, catalog_browse=PricedCatalog())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V2,), slots=CAR_FULL)
    await _act(
        Recommend(reason="revised", exclude_ids=(V2,), refine="cho em mẫu rẻ hơn"),
        state,
        services,
        run_id=RUN_ID,
        user_message="cho em mẫu rẻ hơn",
    )
    # VF 6 đang là 800 triệu → trần mới phải THẤP HƠN đúng chiếc khách vừa chê đắt.
    assert retrieval.criteria[0].budget_max_vnd == Decimal("799999999")


@pytest.mark.asyncio
async def test_xin_cop_rong_hon_thi_day_diem_theo_truc_do() -> None:
    recommendation = SpyRecommendation()
    services = _advisory_services(recommendation=recommendation)
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V2,), slots=CAR_FULL)
    await _act(
        Recommend(reason="revised", exclude_ids=(V2,), refine="cốp rộng hơn được không em"),
        state,
        services,
        run_id=RUN_ID,
        user_message="cốp rộng hơn được không em",
    )
    assert recommendation.seen["traits"] or recommendation.seen["features"]


@pytest.mark.asyncio
async def test_chinh_xong_khong_con_mau_nao_thi_noi_that_khong_lap_lai() -> None:
    class Empty:
        async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
            return []

        async def layer2(self, **_kwargs: Any) -> list:
            return []

    services = _advisory_services(retrieval=Empty())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1,), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="revised", exclude_ids=(V1,), refine="rẻ hơn nữa"),
        state,
        services,
        run_id=RUN_ID,
        user_message="rẻ hơn nữa",
    )
    assert "chưa có mẫu nào khác hợp hơn" in result.text
    assert "VinFast VF 5" in result.text
    assert result.text.count("?") == 1


class VF8Catalog(FakeCatalogBrowse):
    """Đúng bảng giá của lượt prod: VF 5 500 triệu, VF 8 899 triệu."""

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="Dải xe điện hiện có: VF 5, VF 8.",
            pitches=(
                VehiclePitch(
                    vehicle_id=UUID(V1),
                    rank=1,
                    display_name="VinFast VF 5",
                    pitch="x",
                    starting_price_vnd=Decimal("500000000"),
                ),
                VehiclePitch(
                    vehicle_id=UUID(V2),
                    rank=2,
                    display_name="VinFast VF 8",
                    pitch="y",
                    starting_price_vnd=Decimal("899000000"),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_prod_re_hon_duoc_khong_sau_vf8_ra_mau_khac_va_ha_tran() -> None:
    """Lượt prod: đang xem VF 8 (899 triệu), khách hỏi "rẻ hơn được không".
    Trước đây khách nhận lại đúng VF 8 kèm câu `SAME_PICK`."""

    retrieval = FakeRetrieval()
    services = _advisory_services(retrieval=retrieval, catalog_browse=VF8Catalog())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V2,), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="revised", exclude_ids=(V2,), refine="rẻ hơn được không"),
        state,
        services,
        run_id=RUN_ID,
        user_message="rẻ hơn được không",
    )
    assert retrieval.criteria[0].budget_max_vnd < Decimal("899000000")
    # VF 8 rơi khỏi bản đề xuất mới — khách nhận một mẫu KHÁC, không phải câu
    # "vẫn là mẫu vừa rồi".
    assert result.state_patch["recommended_ids"] == (V1,)


@pytest.mark.asyncio
async def test_showroom_doi_ma_tinh_ra_ten_tinh_truoc_khi_tra_toa_do() -> None:
    """Slot giữ MÃ tỉnh ("HN") sau khi `understand` đọc tất định. Đưa thẳng mã
    đó cho service tra toạ độ là gửi một chuỗi máy đi tìm địa danh — không ra
    toạ độ, và lượt lái thử lại về câu "cho em biết vị trí"."""

    from src.agents.domain.nearby_location import UserLocation

    when = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    option = TestDriveSlotOption(
        showroom="VinFast HTA",
        scheduled_at=when,
        label="VinFast HTA - 09:00 ngày 01/09",
        value=_slot_token("VinFast HTA", when),
    )

    class FakeNearbyResolve:
        def __init__(self) -> None:
            self.seen: dict[str, Any] = {}

        async def answer(self, **kwargs: Any) -> FindNearbyLocationResult:
            self.seen.update(kwargs)
            return FindNearbyLocationResult(
                answer="Showroom gần Hà Nội.",
                locations=None,
                resolved_location=UserLocation(latitude=21.0, longitude=105.8),
            )

    nearby = FakeNearbyResolve()
    drive = FakeTestDriveAnswer(slot_options=(option,))
    services = AgentServices(test_drive=drive, nearby_location=nearby, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lịch lái thử")
    assert nearby.seen["location_text"] == "Hà Nội"
    assert drive.seen["known_location"] is not None
    assert len(result.cards["quick_replies"]) >= 1
    assert all(reply.value.startswith("__lichlaithu__|") for reply in result.cards["quick_replies"])


@pytest.mark.asyncio
async def test_nearby_doi_ma_tinh_ra_ten_tinh() -> None:
    class SpyNearby:
        def __init__(self) -> None:
            self.seen: dict[str, Any] = {}

        async def answer(self, **kwargs: Any) -> FindNearbyLocationResult:
            self.seen.update(kwargs)
            return FindNearbyLocationResult(answer="Showroom gần nhất: VinFast HTA.", locations=None)

    nearby = SpyNearby()
    state = _state(slots={N.REGISTRATION_PROVINCE: "HCM"})
    await _act(Nearby(), state, AgentServices(nearby_location=nearby), user_message="showroom gần đây")
    assert nearby.seen["location_text"] == "Hồ Chí Minh"


# ---------- bước 4-5 mục 5: bài đề xuất phải nói ĐÚNG việc khách vừa kể ----------


class SpySynthesis:
    """Ghi lại đúng bộ tham số `act` gửi xuống bộ viết bài."""

    def __init__(self, pitches=None) -> None:
        self.pitches = pitches or (_pitch(V1, "VinFast VF 5"), _pitch(V2, "VinFast VF 6"))
        self.seen: dict[str, Any] = {}

    async def synthesize(self, **kwargs: Any):
        self.seen.update(kwargs)
        return self.pitches


@pytest.mark.asyncio
async def test_synthesis_nhan_chu_khach_va_ma_nhu_cau() -> None:
    synthesis = SpySynthesis()
    services = _advisory_services(synthesis=synthesis)
    state = _state(slots={**CAR_FULL, N.PURPOSE: "đi làm hàng ngày", N.HABIT_NEED_TAGS: ["7_SEATER"]})
    await _act(Recommend(), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert "đi làm hàng ngày" in synthesis.seen["customer_wording"]
    assert "7_SEATER" in synthesis.seen["feature_mention_codes"]
    # Mã máy KHÔNG được lọt vào khối chữ khách — nó phải đã đổi ra nhãn tiếng Việt.
    assert "7_SEATER" not in synthesis.seen["customer_wording"]


@pytest.mark.asyncio
async def test_bai_de_xuat_mo_dau_bang_nhu_cau_that_cua_khach() -> None:
    """Bài prod đọc "có công suất động cơ lớn nhất trong nhóm em vừa chọn… hợp
    với mục đích sử dụng Quý khách chia sẻ" — đúng ngữ pháp, không dính gì tới
    người đang đọc. Câu dẫn TẤT ĐỊNH bảo đảm mỗi xe nói được nhu cầu nào."""

    services = _advisory_services(synthesis=SpySynthesis())
    state = _state(slots={**CAR_FULL, N.PURPOSE: "đi làm hàng ngày", N.PASSENGER_COUNT: 4})
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert "Với nhu cầu đi làm hàng ngày cho 4 người, VinFast VF 5 hợp vì đủ 5 chỗ." in result.text
    assert "Với nhu cầu đi làm hàng ngày cho 4 người, VinFast VF 6 hợp vì đi xa hơn." in result.text
    # Bài của chính bộ viết vẫn còn nguyên — câu dẫn ĐỨNG TRƯỚC, không thay thế.
    assert "VinFast VF 5 rất hợp." in result.text


@pytest.mark.asyncio
async def test_chua_ke_nhu_cau_gi_thi_khong_bia_cau_dan() -> None:
    services = _advisory_services(synthesis=SpySynthesis())
    state = _state(slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert "Với nhu cầu" not in result.text


# ---------- bước 6: biết loại xe thì bày danh sách rồi mới hỏi MỘT câu ----------


@pytest.mark.asyncio
async def test_biet_loai_xe_thi_bay_danh_sach_roi_moi_hoi_mot_cau() -> None:
    """Khách vào bằng "tư vấn ô tô": lõi đã biết loại xe mà vẫn chỉ hỏi một câu
    trống không. Bày danh sách của ĐÚNG loại đó rồi hỏi — trong CÙNG một tin
    nhắn, và câu treo vẫn là `profile` (không phải đổ catalog thay cho câu hỏi)."""

    browse = FakeCatalogBrowse()
    services = AgentServices(catalog_browse=browse)
    state = _state(slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Ask(key="profile", kind=K.SLOT), state, services, user_message="tư vấn ô tô")
    assert "Dải xe điện hiện có: VF 5, VF 6." in result.text
    assert "dùng vào việc gì" in result.text
    assert result.text.index("Dải xe điện") < result.text.index("dùng vào việc gì")
    assert result.state_patch["pending"].key == "profile"
    assert browse.calls[-1]["vehicle_type_hint"] == "CAR"


@pytest.mark.asyncio
async def test_bay_danh_sach_thi_goi_y_la_vi_du_theo_loai_xe() -> None:
    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Ask(key="profile", kind=K.SLOT), state, services, user_message="tư vấn ô tô")
    labels = [reply.label for reply in result.cards["quick_replies"]]
    assert labels[0].startswith("Ô tô khoảng")
    assert "So sánh VinFast VF 5 và VinFast VF 6" in labels


@pytest.mark.asyncio
async def test_chua_biet_loai_xe_thi_van_chi_hoi_mot_cau() -> None:
    browse = FakeCatalogBrowse()
    result = await _act(
        Ask(key="profile", kind=K.SLOT), _state(), AgentServices(catalog_browse=browse), user_message="tư vấn giúp em"
    )
    assert "Dải xe điện" not in result.text
    assert "dùng vào việc gì" in result.text
    assert browse.calls == []


# ---------- prod: đổi tên tỉnh ra toạ độ PHẢI kèm loại địa điểm ----------


class SpyNearbyResolve:
    """`nearby_location` thật: thiếu `location_kinds` thì nó DỪNG ở câu hỏi
    "Quý khách muốn tìm loại địa điểm nào ạ?" và `resolved_location` là `None`."""

    def __init__(self) -> None:
        self.seen: dict[str, Any] = {}

    async def answer(self, **kwargs: Any) -> FindNearbyLocationResult:
        from src.agents.domain.nearby_location import UserLocation

        self.seen.update(kwargs)
        if not kwargs.get("location_kinds"):
            return FindNearbyLocationResult(
                answer="Dạ Quý khách muốn tìm loại địa điểm nào ạ?",
                locations=None,
                needs_location_kind=True,
            )
        return FindNearbyLocationResult(
            answer="Showroom gần Hà Nội.",
            locations=None,
            resolved_location=UserLocation(latitude=21.0, longitude=105.8),
        )


def _drive_services(nearby: SpyNearbyResolve, drive: Any) -> AgentServices:
    return AgentServices(test_drive=drive, nearby_location=nearby, catalog_browse=FakeCatalogBrowse())


def _slot_option() -> TestDriveSlotOption:
    when = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    return TestDriveSlotOption(
        showroom="VinFast HTA",
        scheduled_at=when,
        label="VinFast HTA - 09:00 ngày 01/09",
        value=_slot_token("VinFast HTA", when),
    )


@pytest.mark.asyncio
async def test_doi_ten_tinh_ra_toa_do_kem_loai_dia_diem_o_to() -> None:
    from src.agents.domain.nearby_location import LocationKind

    nearby = SpyNearbyResolve()
    drive = FakeTestDriveAnswer(slot_options=(_slot_option(),))
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    result = await _act(
        ShowroomOptions(vehicle_id=V1), state, _drive_services(nearby, drive), user_message="đặt lịch lái thử"
    )
    assert tuple(nearby.seen["location_kinds"]) == (LocationKind.SHOWROOM_CAR,)
    # Tên tỉnh phải là tên THẬT ("Hà Nội"), không phải bí danh chữ thường.
    assert nearby.seen["location_text"] == "Hà Nội"
    assert drive.seen["known_location"] is not None
    assert len(result.cards["quick_replies"]) >= 1


@pytest.mark.asyncio
async def test_doi_ten_tinh_ra_toa_do_kem_loai_dia_diem_xe_may() -> None:
    from src.agents.domain.nearby_location import LocationKind

    nearby = SpyNearbyResolve()
    drive = FakeTestDriveAnswer(slot_options=(_slot_option(),))
    slots = {N.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE", N.REGISTRATION_PROVINCE: "HCM"}
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots=slots)
    await _act(ShowroomOptions(vehicle_id=V1), state, _drive_services(nearby, drive), user_message="đặt lịch lái thử")
    assert tuple(nearby.seen["location_kinds"]) == (LocationKind.SHOWROOM_MOTORBIKE,)
    assert nearby.seen["location_text"] == "Hồ Chí Minh"


# ---------- prod: có vị trí trình duyệt thì KHÔNG hỏi tỉnh nữa ----------


@pytest.mark.asyncio
async def test_co_vi_tri_trinh_duyet_thi_ra_thang_khung_gio_khong_hoi_tinh() -> None:
    """Lượt prod: khách đã chia sẻ vị trí ở trang bản đồ (`/locations/nearest`
    ghi `user_location` cho phiên), rồi gõ "cho anh lái thử" → lõi vẫn hỏi tỉnh
    vì slot trống. Policy thuần không thấy được vị trí đã lưu; `act` thì thấy."""

    conversation = FakeConversationLocation(_HANOI)
    drive = FakeTestDriveAnswer(slot_options=(_slot_option(),))
    services = AgentServices(test_drive=drive, catalog_browse=FakeCatalogBrowse(), conversation=conversation)
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="cho anh lái thử")
    assert drive.seen["known_location"] is not None
    assert "khu vực nào" not in result.text
    assert len(result.cards["quick_replies"]) >= 1
    assert result.state_patch.get("pending") is None


@pytest.mark.asyncio
async def test_khong_co_vi_tri_nao_thi_act_hoi_tinh_va_treo_dung_slot_do() -> None:
    conversation = FakeConversationLocation(None)
    drive = FakeTestDriveAnswer(slot_options=(_slot_option(),))
    services = AgentServices(test_drive=drive, catalog_browse=FakeCatalogBrowse(), conversation=conversation)
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="cho anh lái thử")
    # Đợt 8: KHÔNG hỏi tỉnh bằng chữ nữa — trả thẻ `needs_location=True` để khách
    # bấm "Dùng vị trí của tôi" / gõ quận huyện ngay trong thẻ. Đường gõ tỉnh vào
    # chat vẫn giữ: pending `registration_province` như cũ.
    assert "trong thẻ" in result.text and "vị trí" in result.text
    card = result.cards["test_drive_card"]
    assert card.needs_location is True and card.vehicle_id == V1 and card.vehicle_name == "VinFast VF 5"
    assert card.showrooms == () and card.days == () and card.options == ()
    assert result.state_patch["pending"].key == N.REGISTRATION_PROVINCE.value
    # Không gọi `test_drive.answer` khi chắc chắn chưa có vị trí: gọi để nhận về
    # đúng câu hỏi vị trí là một vòng service thừa.
    assert drive.seen == {}


@pytest.mark.asyncio
async def test_tra_loi_tinh_xong_thi_ra_nut_khung_gio() -> None:
    """Lượt tiếp theo của case trên: có tỉnh → toạ độ → nút."""

    conversation = FakeConversationLocation(None)
    nearby = SpyNearbyResolve()
    drive = FakeTestDriveAnswer(slot_options=(_slot_option(),))
    services = AgentServices(
        test_drive=drive, catalog_browse=FakeCatalogBrowse(), conversation=conversation, nearby_location=nearby
    )
    state = _state(
        stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR", N.REGISTRATION_PROVINCE: "HN"}
    )
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="Hà Nội")
    assert len(result.cards["quick_replies"]) >= 1
    assert result.state_patch.get("pending") is None


@pytest.mark.asyncio
async def test_hoi_tinh_qua_tran_thi_chuyen_tu_van_vien_khong_hoi_mai() -> None:
    conversation = FakeConversationLocation(None)
    services = AgentServices(
        test_drive=FakeTestDriveAnswer(), catalog_browse=FakeCatalogBrowse(), conversation=conversation
    )
    state = _state(
        stage=Stage.CHOSEN,
        chosen_vehicle_id=V1,
        slots={N.VEHICLE_TYPE: "CAR"},
        ask_counts={N.REGISTRATION_PROVINCE.value: 2},
    )
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="ơ")
    assert result.state_patch["stage"] is Stage.HANDED_OFF


# ---------- prod: không khớp thì TỰ NỚI và nói rõ, luôn có đề xuất ----------


class SeatBlockedRetrieval:
    """Bộ lọc chặt trả về RỖNG cho tới khi điều kiện số chỗ được bỏ.

    Đúng hình lượt prod LP18 ("300 triệu, 5 người, đi làm"): trong tầm 300 triệu
    không mẫu ô tô nào đủ 5 chỗ, nên lọc ra rỗng ở mọi mức ngân sách.
    """

    def __init__(self) -> None:
        self.criteria: list[FilterCriteria] = []

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        self.criteria.append(criteria)
        return [] if criteria.passenger_count is not None else [UUID(V1), UUID(V2)]

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids) -> list:
        return []


LP18 = {N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 300_000_000, N.PASSENGER_COUNT: 5, N.PURPOSE: "đi làm"}


@pytest.mark.asyncio
async def test_khong_khop_thi_tu_noi_tieu_chi_va_noi_ro_da_noi_gi() -> None:
    """Lượt prod LP18: "300 triệu, 5 người, đi làm" → "Em chưa tìm được mẫu nào
    khớp… anh/chị nới ngân sách giúp em". Luật của Sếp: LUÔN có đề xuất — lõi tự
    nới theo thứ tự (ngân sách +20% rồi +40% → bỏ số chỗ → bỏ tiêu chí phụ) và
    NÓI RA đã nới gì, thay vì đẩy việc nới sang cho khách."""

    retrieval = SeatBlockedRetrieval()
    services = _advisory_services(retrieval=retrieval)
    result = await _act(
        Recommend(reason="first"),
        _state(slots=LP18),
        services,
        run_id=RUN_ID,
        user_message="300 triệu, 5 người, đi làm",
    )
    assert result.state_patch["recommended_ids"] == (V1, V2)
    assert "chưa tìm được" not in result.text.lower()
    lead = result.text.splitlines()[0].lower()
    assert "nới" in lead and "420 triệu" in lead and "5 chỗ" in lead
    # Bậc nới chạy ĐÚNG thứ tự: 300 → 360 (+20%) → 420 (+40%) → bỏ số chỗ.
    assert [c.budget_max_vnd for c in retrieval.criteria] == [
        Decimal("300000000"),
        Decimal("360000000"),
        Decimal("420000000"),
        Decimal("420000000"),
    ]
    assert retrieval.criteria[-1].passenger_count is None


@pytest.mark.asyncio
async def test_noi_het_bac_van_khong_co_thi_goi_y_hai_mau_gan_gia_nhat() -> None:
    """Bậc cuối: không mẫu nào khớp kể cả sau khi nới → hai mẫu gần giá nhất của
    ĐÚNG loại xe đó, chứ không phải một câu bảo khách tự nới ngân sách."""

    class Empty:
        async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
            return []

        async def layer2(self, **_kwargs: Any) -> list:
            return []

    services = _advisory_services(retrieval=Empty(), catalog_browse=PricedCatalog())
    result = await _act(
        Recommend(reason="first"), _state(slots=LP18), services, run_id=RUN_ID, user_message="300 triệu, 5 người"
    )
    assert "VinFast VF 5" in result.text and "500 triệu" in result.text
    assert "nới ngân sách một chút giúp em" not in result.text


@pytest.mark.asyncio
async def test_doi_loai_xe_thi_bai_de_xuat_mo_dau_bang_cau_chuyen_loai() -> None:
    """Khách vừa đổi sang xe máy điện: dòng đầu phải nói ra việc chuyển loại,
    nếu không thì bài mới trông y như lõi lờ mất câu "thôi xe máy đi"."""

    services = _advisory_services()
    state = _state(slots={N.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE", N.BUDGET_MAX_VND: 30_000_000})
    result = await _act(
        Recommend(reason="slots_changed", switched_type="ELECTRIC_MOTORBIKE"),
        state,
        services,
        run_id=RUN_ID,
        user_message="thôi xe máy đi",
    )
    assert result.text.splitlines()[0].startswith("Dạ, em chuyển sang xe máy điện")


# ---------- prod: nút khung giờ hết hiệu lực ----------


@pytest.mark.asyncio
async def test_nut_het_hieu_luc_thi_noi_ro_va_goi_y_lai_khung_gio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mã hết hạn/không đúng chữ ký: nói thật rồi BÀY LẠI khung giờ mới, thay vì
    hỏi "muốn xem mẫu nào" (lượt prod LP21) hay im lặng."""

    import src.agents.core.act as act_module

    monkeypatch.setattr(act_module, "read_slot_token", lambda message, **_kwargs: None)
    when = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
    options = (
        TestDriveSlotOption(
            showroom="VinFast HTA", scheduled_at=when, label="9:00 30/08 — VinFast HTA", value="__lichlaithu__|a|b"
        ),
    )
    drive = FakeTestDriveAnswer(slot_options=options)
    services = AgentServices(
        test_drive=drive, catalog_browse=FakeCatalogBrowse(), conversation=FakeConversationLocation(_HANOI)
    )
    state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(
        Book(vehicle_id=V1, choice_ref="__lichlaithu__|cu|roi"), state, services, user_message="__lichlaithu__|cu|roi"
    )
    assert "hết hiệu lực" in result.text
    assert "VinFast HTA" in result.text
    assert [reply.value for reply in result.cards["quick_replies"]] == ["__lichlaithu__|a|b"]
    assert result.state_patch.get("stage") is not Stage.CHOSEN


@pytest.mark.asyncio
async def test_nut_het_hieu_luc_ma_chua_biet_xe_thi_hoi_mau_nao(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agents.core.act as act_module

    monkeypatch.setattr(act_module, "read_slot_token", lambda message, **_kwargs: None)

    class NeverAnswer:
        async def answer(self, **_kwargs: Any):  # pragma: no cover - phải không bao giờ chạy
            raise AssertionError("chưa biết xe thì không gọi được showroom")

    services = AgentServices(test_drive=NeverAnswer(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots=CAR_FULL)
    result = await _act(Book(vehicle_id="", choice_ref="rác"), state, services, user_message="rác")
    assert "hết hiệu lực" in result.text
    assert "VinFast VF 5" in result.text and V1 not in result.text
    assert result.state_patch["pending"].key == "vehicle"


# ---------- prod vòng 7 (LP21): nút khung giờ là TIN NHẮN ĐẦU của phiên ----------


LP21_TOKEN = "__lichlaithu__|2026-08-29T10:00:00+07:00|VinFast E-Car Hưng Yên"


@pytest.mark.asyncio
async def test_nut_khung_gio_cu_o_dau_phien_khong_lam_no_luot() -> None:
    """Lượt prod LP21: tin nhắn ĐẦU của phiên là mã nút của một lượt cũ (ba mảnh,
    mảnh cuối là tên showroom có dấu). `hmac.compare_digest` ném `TypeError` khi
    so chuỗi ngoài ASCII, `act` nổ, và `run_turn` trả câu an toàn của chặng
    GREETING — "anh/chị đang tìm ô tô điện hay xe máy điện ạ?" — không dính gì
    tới cái nút khách vừa bấm. Mã hỏng phải nói THẬT là hết hiệu lực."""

    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.GREETING)
    result = await _act(Book(vehicle_id="", choice_ref=LP21_TOKEN), state, services, user_message=LP21_TOKEN)
    assert "hết hiệu lực" in result.text
    assert "mẫu nào" in result.text
    assert "ô tô điện hay xe máy điện" not in result.text
    assert result.state_patch["pending"].key == "vehicle"


@pytest.mark.asyncio
async def test_nut_khung_gio_cu_o_dau_phien_ma_da_biet_xe_thi_bay_lai_khung_gio() -> None:
    when = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
    options = (
        TestDriveSlotOption(
            showroom="VinFast HTA", scheduled_at=when, label="9:00 30/08 — VinFast HTA", value="__lichlaithu__|a|b"
        ),
    )
    services = AgentServices(
        test_drive=FakeTestDriveAnswer(slot_options=options),
        catalog_browse=FakeCatalogBrowse(),
        conversation=FakeConversationLocation(_HANOI),
    )
    state = _state(stage=Stage.GREETING, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(Book(vehicle_id="", choice_ref=LP21_TOKEN), state, services, user_message=LP21_TOKEN)
    assert "hết hiệu lực" in result.text and "VinFast HTA" in result.text


# ---------- prod vòng 7 (LP15/16/19/31): câu "vẫn là mẫu cũ" phải kèm THẺ XE ----------


@pytest.mark.asyncio
async def test_van_la_mau_cu_thi_van_giu_the_xe() -> None:
    """Lượt prod LP15/16/19/31: "Với tiêu chí anh/chị vừa nêu, em vẫn thấy VF 3
    hợp nhất…" đi ra với `recommendations=[]`, nên màn hình khách chỉ còn chữ —
    thẻ xe của lượt trước đã cuộn đi mất. Câu ngắn thì không đọc lại bài, nhưng
    THẺ thì vẫn phải có: đó là thứ khách bấm để đi tiếp."""

    services = _advisory_services()
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="slots_changed"), state, services, run_id=RUN_ID, user_message="thế còn mẫu nào"
    )
    views = result.cards["recommendations"]
    assert [str(view.vehicle_id) for view in views] == [V1, V2]
    assert [view.rank for view in views] == [1, 2]
    assert views[0].display_name == "VinFast VF 5"


@pytest.mark.asyncio
async def test_retry_het_xe_moi_van_giu_the_xe_dang_xem() -> None:
    services = _advisory_services()
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="retry", exclude_ids=(V1, V2)), state, services, run_id=RUN_ID, user_message="mẫu khác đi em"
    )
    assert "vẫn thấy" in result.text
    assert [str(view.vehicle_id) for view in result.cards["recommendations"]] == [V1, V2]


@pytest.mark.asyncio
async def test_khong_co_mau_nao_hop_hon_van_giu_the_xe() -> None:
    """Đường `refine` cũng là một lượt đề xuất: nói "chưa có mẫu nào hợp hơn"
    mà bỏ luôn thẻ xe là bắt khách cuộn ngược lên tìm mẫu đang nói tới."""

    class Empty:
        async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
            return []

        async def layer2(self, **_kwargs: Any) -> list:
            return []

    services = _advisory_services(retrieval=Empty())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1,), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="revised", exclude_ids=(V1,), refine="rẻ hơn nữa được không"),
        state,
        services,
        run_id=RUN_ID,
        user_message="rẻ hơn nữa được không",
    )
    assert "hợp hơn" in result.text
    assert [str(view.vehicle_id) for view in result.cards["recommendations"]] == [V1]


@pytest.mark.asyncio
async def test_the_xe_khong_co_trong_catalog_thi_bo_qua_khong_no() -> None:
    """Id không có trong catalog (catalog vừa đổi, id rác trong state): bỏ thẻ
    đó đi, KHÔNG dựng thẻ rỗng và cũng không làm hỏng câu trả lời."""

    class Empty:
        async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
            return []

        async def layer2(self, **_kwargs: Any) -> list:
            return []

    services = _advisory_services(retrieval=Empty())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=("khong-phai-uuid",), slots=CAR_FULL)
    result = await _act(
        Recommend(reason="retry", exclude_ids=("khong-phai-uuid",)),
        state,
        services,
        run_id=RUN_ID,
        user_message="mẫu khác",
    )
    assert "vẫn thấy" in result.text
    assert list(result.cards.get("recommendations", [])) == []


# ---------- prod vòng 8: giá lăn bánh sau khi khách đáp TÊN TỈNH ----------


@pytest.mark.asyncio
@pytest.mark.parametrize("said", ["Hà Nội", "hn", "ở Hà Nội ạ", "Hà Nội nhé em"])
async def test_gia_lan_banh_cau_mang_ten_tinh_van_ra_dung_khu_vuc(said: str) -> None:
    """Giữ tinh thần bài prod vòng 8: tên tỉnh trong CÂU phải ra đúng khu vực
    phí — giờ soi qua `region_code` gửi cho `tco_estimation` (thẻ chi phí),
    không còn soi câu gửi cho service chữ (đường đó đã bỏ 2026-08-31)."""

    service = FakeTcoForOnRoad()
    services = AgentServices(tco_estimation=service, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(OnRoadPrice(vehicle_id=V1), state, services, user_message=said)
    assert service.seen["region"] == "KHU_VUC_I"
    assert result.cards["tco_card"].province_code == "HN"


@pytest.mark.asyncio
async def test_gia_lan_banh_tinh_khach_vua_noi_thang_tinh_trong_slot() -> None:
    """Khách đáp một tỉnh KHÁC tỉnh đang có trong slot: tỉnh vừa nói là tỉnh đúng."""

    service = FakeTcoForOnRoad()
    services = AgentServices(tco_estimation=service, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    result = await _act(OnRoadPrice(vehicle_id=V1), state, services, user_message="em ở Đà Nẵng")
    assert service.seen["region"] == "KHU_VUC_II"
    assert result.cards["tco_card"].province_code == "DN"


# ---------- prod vòng 8: tra cứu CÓ tên xe không được đổ cả danh mục ----------


class NameOnlyCatalogBrowse(FakeCatalogBrowse):
    """Cửa danh mục chỉ còn được dùng để TRA TÊN xe (`catalog_names`, câu rỗng).

    Đưa CÂU CỦA KHÁCH vào đây là đi đường duyệt danh mục — đúng lỗi prod vòng 8.
    """

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        if user_message.strip():
            raise AssertionError("tra cứu một mẫu cụ thể mà lại đổ cả danh mục")
        return await super().answer(user_message=user_message, vehicle_type_hint=vehicle_type_hint)


@pytest.mark.asyncio
async def test_tra_cuu_kem_ten_xe_tra_loi_ve_xe_do_khong_do_danh_muc() -> None:
    """Lượt prod vòng 8: "VF 3 giá bao nhiêu" → `CATALOG_LOOKUP, vehicle_ids=[VF3]`
    → `act` gọi `catalog_browse` và khách nhận danh sách 27 ô tô + 7 xe máy.
    Đã trỏ ra được một chiếc thì câu trả lời phải nói về CHIẾC ĐÓ."""

    overview = FakeOverview("VinFast VF 5 giá niêm yết 529 triệu đồng.")
    services = AgentServices(vehicle_overview=overview, catalog_browse=NameOnlyCatalogBrowse())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(
        Lookup(mode=LOOKUP_LOOKUP, vehicle_ids=(V1,)), state, services, user_message="VF 5 giá bao nhiêu"
    )
    assert overview.asked == ["VinFast VF 5"]
    body, _, closing = result.text.partition("\n\n")
    assert "529 triệu" in body
    assert "VF 6" not in body
    # Đợt 9: chưa chốt xe, đang có đề xuất → câu kết mời ưng mẫu đầu hay so với mẫu hai.
    assert closing == "Anh/chị ưng VinFast VF 5 không, hay để em so với VinFast VF 6 cho dễ quyết?"


@pytest.mark.asyncio
async def test_tra_cuu_kem_ten_xe_ma_khong_co_fact_thi_noi_that() -> None:
    """Không có dữ liệu về mẫu đó thì nói thật — KHÔNG lui về đổ danh mục."""

    services = AgentServices(vehicle_overview=FakeOverview(None), catalog_browse=NameOnlyCatalogBrowse())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1,), slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(
        Lookup(mode=LOOKUP_LOOKUP, vehicle_ids=(V1,)), state, services, user_message="VF 5 giá bao nhiêu"
    )
    assert "tư vấn viên" in result.text.lower()


@pytest.mark.asyncio
async def test_tra_cuu_khong_ten_xe_van_di_duong_danh_muc() -> None:
    browse = FakeCatalogBrowse()
    services = AgentServices(catalog_browse=browse, vehicle_overview=FakeOverview(None))
    state = _state(stage=Stage.COLLECTING, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Lookup(mode=LOOKUP_LOOKUP), state, services, user_message="có những xe nào")
    assert browse.calls == [{"user_message": "có những xe nào", "vehicle_type_hint": "CAR"}]
    assert "VF 5" in result.text


# ---------- prod vòng 8: đề xuất sau khi NỚI tiêu chí vẫn phải kèm thẻ xe ----------


class MotorbikeCatalog(FakeCatalogBrowse):
    """Danh mục trả xe MÁY chỉ khi được hỏi ĐÚNG loại đó.

    Loại xe của lượt này là loại SUY ra từ ngân sách (slot trống), nên đọc thẻ
    theo `slots[VEHICLE_TYPE]` sẽ hỏi nhầm sang ô tô và không thẻ nào khớp id.
    """

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        self.calls.append({"user_message": user_message, "vehicle_type_hint": vehicle_type_hint})
        if vehicle_type_hint != "ELECTRIC_MOTORBIKE":
            return CatalogBrowseResult(answer="Dải ô tô điện hiện có: VF 5.", pitches=())
        return CatalogBrowseResult(
            answer="Xe máy điện hiện có: Evo200, Klara S.",
            pitches=(
                VehiclePitch(
                    vehicle_id=UUID(V1),
                    rank=1,
                    display_name="VinFast Evo200",
                    pitch="x",
                    starting_price_vnd=Decimal("22000000"),
                ),
                VehiclePitch(
                    vehicle_id=UUID(V2),
                    rank=2,
                    display_name="VinFast Klara S",
                    pitch="y",
                    starting_price_vnd=Decimal("40000000"),
                ),
            ),
        )


class BudgetBlockedRetrieval:
    """Bộ lọc chặt rỗng cho tới khi ngân sách được nới lên (lượt prod "tầm 30 triệu")."""

    def __init__(self) -> None:
        self.criteria: list[FilterCriteria] = []

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        self.criteria.append(criteria)
        if criteria.budget_max_vnd is not None and criteria.budget_max_vnd < Decimal("40000000"):
            return []
        return [UUID(V1), UUID(V2)]

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids) -> list:
        return []


@pytest.mark.asyncio
async def test_de_xuat_sau_khi_noi_tieu_chi_van_kem_the_xe() -> None:
    """Lượt prod vòng 8: "tầm 30 triệu" (xe máy) → lõi nới ngân sách, viết được
    bài, nhưng `recommendations=[]` — khách đọc "Em gợi ý anh/chị mấy mẫu sau ạ:"
    mà màn hình không có thẻ nào để bấm. Đường dự phòng (synthesis không có /
    hỏng / verify trượt) trước đây trả THẲNG danh sách thẻ rỗng."""

    services = _advisory_services(retrieval=BudgetBlockedRetrieval(), synthesis=None, catalog_browse=MotorbikeCatalog())
    state = _state(slots={N.BUDGET_MAX_VND: 30_000_000})
    result = await _act(Recommend(reason="first"), state, services, run_id=RUN_ID, user_message="tầm 30 triệu")
    assert "nới" in result.text.splitlines()[0].lower()
    assert len(result.cards["recommendations"]) >= 1
    assert result.cards["recommendations"][0].display_name == "VinFast Evo200"


@pytest.mark.asyncio
async def test_bai_du_phong_khi_verify_truot_van_kem_the_xe() -> None:
    """Cùng một lỗ: bộ viết chạy nhưng kiểm chứng trượt → đường dự phòng."""

    class Reject:
        async def verify(self, **_kwargs: Any) -> bool:
            return False

    services = _advisory_services(verification=Reject(), catalog_browse=PricedCatalog())
    result = await _act(
        Recommend(reason="first"), _state(slots=CAR_FULL), services, run_id=RUN_ID, user_message="tư vấn xe"
    )
    assert len(result.cards["recommendations"]) >= 1


@pytest.mark.asyncio
async def test_bac_cuoi_gan_gia_nhat_cung_kem_the_xe() -> None:
    """Bậc CUỐI (hai mẫu gần giá nhất) cũng phải có thẻ, và hai mẫu đó phải vào
    `recommended_ids` — không thì lượt sau khách bấm/chọn chúng lại bị hỏi lại
    "muốn xem mẫu nào"."""

    class Empty:
        async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
            return []

        async def layer2(self, **_kwargs: Any) -> list:
            return []

    services = _advisory_services(retrieval=Empty(), catalog_browse=PricedCatalog())
    result = await _act(
        Recommend(reason="first"), _state(slots=LP18), services, run_id=RUN_ID, user_message="300 triệu, 5 người"
    )
    assert len(result.cards["recommendations"]) >= 1
    assert result.state_patch["recommended_ids"]


# ---------- prod vòng 9: "có hợp với nhu cầu của tôi không" ----------


def _facts(vehicle_id: str, name: str, **specs: Any) -> VehicleFacts:
    price = specs.pop("price", None)
    return VehicleFacts(
        vehicle_id=UUID(vehicle_id),
        display_name=name,
        vehicle_type=VehicleType.CAR,
        starting_price_vnd=Decimal(str(price)) if price is not None else None,
        specs=dict(specs),
    )


class FakeFitCatalog:
    """Hai mẫu có tên — `catalog_names`/`catalog_cards` đọc từ đây."""

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="Dải xe: VF 2, VF 5.",
            pitches=(_pitch(V1, "VinFast VF 2"), _pitch(V2, "VinFast VF 5")),
        )


class FakeFitOverview:
    def __init__(self, by_name: dict[str, VehicleFacts]) -> None:
        self.by_name = by_name
        self.asked: list[str] = []

    async def answer(self, *, vehicle_name: str, session_id: str) -> VehicleOverviewResult:
        self.asked.append(vehicle_name)
        facts = self.by_name.get(vehicle_name)
        return VehicleOverviewResult(overview=None, answer="tổng quan", lookup_facts=(facts,) if facts else ())


FIT_SLOTS = {
    N.VEHICLE_TYPE: "CAR",
    N.BUDGET_MAX_VND: 500_000_000,
    N.PURPOSE: "đi chơi xa cùng gia đình",
    N.PASSENGER_COUNT: 4,
}


def _fit_services() -> tuple[AgentServices, FakeFitOverview]:
    overview = FakeFitOverview(
        {
            "VinFast VF 2": _facts(
                V1, "VinFast VF 2", seat_count=4, range_km="210", cargo_volume_standard_l=200, price=260_000_000
            ),
            "VinFast VF 5": _facts(
                V2, "VinFast VF 5", seat_count=5, range_km="326", cargo_volume_standard_l=300, price=480_000_000
            ),
        }
    )
    return AgentServices(catalog_browse=FakeFitCatalog(), vehicle_overview=overview), overview


@pytest.mark.asyncio
async def test_fit_check_doi_chieu_so_that_va_goi_y_mau_va_duoc_cho_thieu() -> None:
    services, _ = _fit_services()
    state = _state(stage=Stage.CHOSEN, slots=FIT_SLOTS, chosen_vehicle_id=V1, recommended_ids=(V1, V2))
    result = await _act(FitCheck(vehicle_id=V1, alternative_ids=(V1, V2), just_chosen=True), state, services)
    assert "em ghi nhận anh/chị chọn VinFast VF 2" in result.text
    assert "hợp một phần" in result.text
    assert "210 km" in result.text
    assert "VinFast VF 5" in result.text
    views = result.cards["recommendations"]
    assert [str(view.vehicle_id) for view in views] == [V2]


@pytest.mark.asyncio
async def test_fit_check_du_moi_tieu_chi_thi_khong_moi_doi_mau() -> None:
    services, overview = _fit_services()
    state = _state(stage=Stage.CHOSEN, slots={N.VEHICLE_TYPE: "CAR", N.PASSENGER_COUNT: 4}, chosen_vehicle_id=V2)
    result = await _act(FitCheck(vehicle_id=V2, alternative_ids=(V1,)), state, services)
    assert "VinFast VF 5 hợp ạ" in result.text
    # Lượt "hợp" KHÔNG được tốn thêm một vòng đọc catalog cho mẫu thay thế.
    assert overview.asked == ["VinFast VF 5"]
    assert "recommendations" not in result.cards


@pytest.mark.asyncio
async def test_fit_check_khong_co_so_lieu_thi_noi_that() -> None:
    services = AgentServices(catalog_browse=FakeFitCatalog(), vehicle_overview=FakeFitOverview({}))
    state = _state(stage=Stage.CHOSEN, slots=FIT_SLOTS, chosen_vehicle_id=V1)
    result = await _act(FitCheck(vehicle_id=V1), state, services)
    assert "chưa có trong dữ liệu đã kiểm chứng" in result.text


class FakeFitRetrieval:
    """Lớp 1 của lượt lọc lại theo tiêu chí MỚI."""

    def __init__(self, ids: tuple[str, ...]) -> None:
        self.ids = ids
        self.criteria: list[FilterCriteria] = []

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        self.criteria.append(criteria)
        return [UUID(value) for value in self.ids]


@pytest.mark.asyncio
async def test_fit_check_loc_lai_theo_tieu_chi_moi_khi_bo_de_xuat_cu_khong_va_duoc() -> None:
    """Khách vừa kể thêm "4 người, đi chơi xa": mẫu vá được chỗ thiếu có thể
    chưa từng nằm trong `recommended_ids` cũ, nên phải lọc lại catalog."""

    services, _ = _fit_services()
    retrieval = FakeFitRetrieval((V2,))
    services = AgentServices(
        catalog_browse=services.catalog_browse, vehicle_overview=services.vehicle_overview, retrieval=retrieval
    )
    state = _state(stage=Stage.CHOSEN, slots=FIT_SLOTS, chosen_vehicle_id=V1, recommended_ids=(V1,))
    result = await _act(FitCheck(vehicle_id=V1, alternative_ids=(V1,)), state, services)
    assert "VinFast VF 5" in result.text
    assert retrieval.criteria and retrieval.criteria[0].passenger_count == 4


def _column(vehicle_id: str, name: str, **specs: Any) -> ComparedVehicleView:
    price = specs.pop("price", None)
    return ComparedVehicleView(
        vehicle_id=vehicle_id,
        found=True,
        display_name=name,
        vehicle_type="CAR",
        starting_price_vnd=str(price) if price is not None else None,
        specs={key: str(value) for key, value in specs.items()},
    )


class FakeCompareTable:
    """Bảng so sánh CÓ số — đúng hình `compare_vehicles.answer` trả về."""

    def __init__(self, comparison: VehicleComparisonView | None) -> None:
        self.comparison = comparison

    async def answer(self, *, user_message: str, vehicle_names: Any) -> CompareVehiclesResult:
        return CompareVehiclesResult(answer="Bảng so sánh hai mẫu.", comparison=self.comparison, follow_up=None)


COMPARE_TABLE = VehicleComparisonView(
    vehicles=[
        _column(V1, "VinFast VF 2", seat_count=4, range_km="210", cargo_volume_standard_l=200, price=260_000_000),
        _column(V2, "VinFast VF 5", seat_count=5, range_km="326", cargo_volume_standard_l=300, price=480_000_000),
    ]
)


@pytest.mark.asyncio
async def test_compare_mo_dau_bang_ket_luan_theo_nhu_cau() -> None:
    """Lượt prod vòng 9: "VF2 với VF3 thì cái nào hợp với nhu cầu của tôi hơn"
    — bảng số đặt cạnh nhau không trả lời câu hỏi xếp hạng của khách."""

    services = AgentServices(catalog_browse=FakeFitCatalog(), compare_vehicles=FakeCompareTable(COMPARE_TABLE))
    state = _state(stage=Stage.RECOMMENDED, slots=FIT_SLOTS, recommended_ids=(V1, V2))
    result = await _act(Compare(vehicle_ids=(V1, V2)), state, services, user_message="cái nào hợp hơn")
    first_line = result.text.splitlines()[0]
    assert "VinFast VF 5 hợp hơn VinFast VF 2" in first_line
    assert "Bảng so sánh hai mẫu." in result.text
    assert result.cards["comparison"] is COMPARE_TABLE


@pytest.mark.asyncio
async def test_compare_khong_biet_nhu_cau_thi_khong_them_dong_ket_luan() -> None:
    services = AgentServices(catalog_browse=FakeFitCatalog(), compare_vehicles=FakeCompareTable(COMPARE_TABLE))
    state = _state(stage=Stage.RECOMMENDED, slots={N.VEHICLE_TYPE: "CAR"}, recommended_ids=(V1, V2))
    result = await _act(Compare(vehicle_ids=(V1, V2)), state, services, user_message="so sánh hai xe")
    assert result.text == "Bảng so sánh hai mẫu."


@pytest.mark.asyncio
async def test_compare_khong_co_bang_so_thi_van_chay_nhu_cu() -> None:
    services = AgentServices(catalog_browse=FakeFitCatalog(), compare_vehicles=FakeCompareTable(None))
    state = _state(stage=Stage.RECOMMENDED, slots=FIT_SLOTS, recommended_ids=(V1, V2))
    result = await _act(Compare(vehicle_ids=(V1, V2)), state, services, user_message="so sánh")
    assert result.text == "Bảng so sánh hai mẫu."


@pytest.mark.asyncio
async def test_next_steps_ke_ba_buoc_va_kem_nut_bam_duoc() -> None:
    services = AgentServices(catalog_browse=FakeFitCatalog())
    state = _state(stage=Stage.CHOSEN, slots=FIT_SLOTS, chosen_vehicle_id=V1)
    result = await _act(NextSteps(vehicle_id=V1), state, services)
    assert "để chốt VinFast VF 2" in result.text
    assert "lái thử" in result.text and "cọc" in result.text
    assert [view.label for view in result.cards["quick_replies"]] == ["Đặt lịch lái thử", "Có ưu đãi gì không?"]


@pytest.mark.asyncio
async def test_scope_note_noi_that_kem_tam_chay_that_cua_xe() -> None:
    services, _ = _fit_services()
    state = _state(stage=Stage.CHOSEN, slots=FIT_SLOTS, chosen_vehicle_id=V1)
    result = await _act(ScopeNote(vehicle_id=V1), state, services, user_message="đi du lịch ở đâu")
    assert "chỉ rành về xe" in result.text
    assert "210 km" in result.text
    assert "hợp hơn" not in result.text


@pytest.mark.asyncio
async def test_scope_note_khong_co_so_lieu_van_noi_that() -> None:
    services = AgentServices(catalog_browse=FakeFitCatalog(), vehicle_overview=FakeFitOverview({}))
    state = _state(stage=Stage.CHOSEN, slots=FIT_SLOTS, chosen_vehicle_id=V1)
    result = await _act(ScopeNote(vehicle_id=V1), state, services, user_message="đi du lịch ở đâu")
    assert "chỉ rành về xe" in result.text
    assert "VinFast VF 2" in result.text


# ---------- prod vòng 10: "đi chơi xa" phải kéo TẦM CHẠY vào kết luận ----------


@pytest.mark.asyncio
async def test_fit_check_doc_nhu_cau_tu_chinh_cau_khach_vua_go() -> None:
    """Lượt prod vòng 10: đã chọn VF 2, khách gõ "gia đình tôi có 4 người, tôi
    muốn sử dụng đi chơi xa" và lõi kết luận "hợp: 4 chỗ, giá trong ngân sách".
    Slot lượt đó chỉ có số người (LLM đọc câu là một lời khai số chỗ), nên nếu
    chỉ đọc slot thì cụm "đi chơi xa" — và tầm chạy 210 km — biến mất."""

    services, _ = _fit_services()
    slots = {N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 500_000_000, N.PASSENGER_COUNT: 4}
    state = _state(stage=Stage.CHOSEN, slots=slots, chosen_vehicle_id=V1, recommended_ids=(V1, V2))
    result = await _act(
        FitCheck(vehicle_id=V1, alternative_ids=(V1, V2)),
        state,
        services,
        user_message="gia đình tôi có 4 người, tôi muốn sử dụng đi chơi xa",
    )
    assert "hợp một phần" in result.text
    assert "210 km" in result.text and "sạc dọc đường" in result.text
    assert "VinFast VF 5" in result.text


LONG_TRIP_TABLE = VehicleComparisonView(
    vehicles=[
        _column(V1, "VinFast VF 5", seat_count=5, range_km="326", cargo_volume_standard_l=300, price=480_000_000),
        _column(V2, "VinFast VF 8", seat_count=5, range_km="470", cargo_volume_standard_l=376, price=490_000_000),
    ]
)


@pytest.mark.asyncio
async def test_compare_khach_di_xa_thi_tam_chay_pha_the_ngang_nhau() -> None:
    """Hai mẫu cùng đạt hết tiêu chí đếm được → dòng kết luận cũ đọc "bám sát
    ngang nhau". Với người vừa nói "đi chơi xa" thì 326 km và 470 km không phải
    là ngang nhau, và dòng kết luận phải nói ra chính con số đó."""

    services = AgentServices(catalog_browse=FakeFitCatalog(), compare_vehicles=FakeCompareTable(LONG_TRIP_TABLE))
    state = _state(stage=Stage.RECOMMENDED, slots=FIT_SLOTS, recommended_ids=(V1, V2))
    result = await _act(Compare(vehicle_ids=(V1, V2)), state, services, user_message="cái nào hợp hơn")
    first_line = result.text.splitlines()[0]
    assert "VinFast VF 8 hợp hơn VinFast VF 5" in first_line
    assert "470" in first_line


@pytest.mark.asyncio
async def test_cau_dan_bai_de_xuat_doc_ca_the_nhu_cau_di_xa() -> None:
    """Khách chưa gõ mục đích bằng chữ, nhưng thẻ nhu cầu đã nói họ đi xa — câu
    dẫn phải nói lại đúng việc đó thay vì im lặng."""

    services = _advisory_services(synthesis=SpySynthesis())
    state = _state(slots={**CAR_FULL, N.PURPOSE: "", N.HABIT_NEED_TAGS: ["LONG_RANGE"], N.PASSENGER_COUNT: 4})
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert "Với nhu cầu đi xa cho 4 người" in result.text


# ---------- đợt 8: câu dẫn không khớp need-tag nào thì dùng SỐ THẬT ----------


class FillerReasonRecommendation(FakeRecommendation):
    """Lý do chấm điểm CHỈ có claim loại xe — đúng hình lượt prod "đi rạo"."""

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes=(),
        preferred_trait_codes=(),
        vehicle_type=None,
        budget_relaxed: bool = False,
    ) -> list[Recommendation]:
        return [
            Recommendation(
                vehicle_id=UUID(V1),
                rank=1,
                reasons=["[slot=vehicle_type] Đúng loại phương tiện CAR đã chọn"],
                display_name="VinFast VF 3 All New",
            ),
        ]


@pytest.mark.asyncio
async def test_cau_dan_khong_khop_need_tag_thi_dung_so_that_cua_xe() -> None:
    """Prod benchmark2 (2026-08-30): "đi rạo" (lỗi gõ) không khớp need-tag nào,
    bài đề xuất thành "Với nhu cầu đi rạo, VinFast VF 3 All New hợp vì thuộc
    đúng dòng xe Quý khách đang tìm." lặp cho ba xe. Câu dẫn phải dùng giá từ,
    số chỗ, tầm chạy THẬT — và toàn lõi v2 xưng anh/chị."""

    overview = FakeFitOverview(
        {"VinFast VF 3 All New": _facts(V1, "VinFast VF 3 All New", seat_count=4, range_km="215", price=278_000_000)}
    )
    services = _advisory_services(
        recommendation=FillerReasonRecommendation(),
        synthesis=SpySynthesis(pitches=(_pitch(V1, "VinFast VF 3 All New"),)),
        vehicle_overview=overview,
    )
    state = _state(slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 300_000_000, N.PURPOSE: "đi rạo"})
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="đi rạo")
    assert "Quý khách" not in result.text
    assert "dòng xe" not in result.text
    assert "Với nhu cầu đi rạo, VinFast VF 3 All New" in result.text
    assert "278 triệu" in result.text and "4 chỗ" in result.text and "215 km" in result.text


# ---------- đợt 8: hỏi GIÁ một mẫu → trả giá trước, không đổ cả bảng thông số ----------


class PriceOnlyVF8Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(answer="Dải xe: VF 8.", pitches=(_pitch(V1, "VinFast VF 8"),))


@pytest.mark.asyncio
async def test_tra_cuu_khia_canh_gia_tra_gia_niem_yet_truoc() -> None:
    """Prod benchmark2: "giá con vf8 mới" nhận nguyên bảng thông số dài. Khách
    hỏi GIÁ thì câu đầu phải là giá niêm yết, kèm ba lối đi tiếp có tên xe."""

    from src.agents.core.actions import ASPECT_PRICE

    overview = FakeFitOverview(
        {"VinFast VF 8": _facts(V1, "VinFast VF 8", seat_count=5, range_km="471", price=899_000_000)}
    )
    services = AgentServices(vehicle_overview=overview, catalog_browse=PriceOnlyVF8Catalog())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1,), slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(
        Lookup(mode=LOOKUP_LOOKUP, vehicle_ids=(V1,), aspect=ASPECT_PRICE),
        state,
        services,
        user_message="giá con vf8 mới",
    )
    assert result.text.startswith("VinFast VF 8: giá niêm yết từ 899.000.000đ (đã VAT).")
    assert "lăn bánh" in result.text and "5 năm" in result.text
    assert "động cơ" not in result.text.lower()
    assert [reply.label for reply in result.cards["quick_replies"]] == [
        "Giá lăn bánh VF 8",
        "Tính chi phí VF 8",
        "Đặt lái thử VF 8",
    ]
    assert result.cards["lookup_facts"], "thẻ số liệu vẫn đi kèm để client bày giá"


@pytest.mark.asyncio
async def test_tra_cuu_khia_canh_gia_ma_khong_co_gia_thi_ve_bang_thong_so() -> None:
    from src.agents.core.actions import ASPECT_PRICE

    overview = FakeOverview("VinFast VF 8: động cơ 150 kW, ADAS.")
    services = AgentServices(vehicle_overview=overview, catalog_browse=PriceOnlyVF8Catalog())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1,), slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(
        Lookup(mode=LOOKUP_LOOKUP, vehicle_ids=(V1,), aspect=ASPECT_PRICE), state, services, user_message="giá vf8"
    )
    assert "động cơ" in result.text


# ---------- đợt 8: tên xe không có trong danh mục → nói thật + bày danh mục ----------


@pytest.mark.asyncio
async def test_not_in_catalog_noi_that_bay_danh_muc_va_treo_chon_mau() -> None:
    from src.agents.core.actions import NotInCatalog

    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    pending = Pending(kind=K.CHOICE, key="vehicle", asked_at_turn=1)
    state = _state(stage=Stage.COLLECTING, slots={N.VEHICLE_TYPE: "CAR"}, pending=pending, turn_count=1)
    result = await _act(NotInCatalog(mention="VF 10"), state, services, user_message="anh muốn mua mẫu vf10")
    assert "Em chưa thấy 'VF 10' trong danh mục VinFast hiện hành ạ." in result.text
    assert "VF 5, VF 6" in result.text
    assert "ngân sách" in result.text
    assert [card.display_name for card in result.cards["recommendations"]] == ["VinFast VF 5", "VinFast VF 6"]
    assert [reply.label for reply in result.cards["quick_replies"]] == ["VF 5", "VF 6"]
    saved = result.state_patch["pending"]
    assert saved.key == "vehicle" and saved.options == (V1, V2) and saved.labels == ("VinFast VF 5", "VinFast VF 6")
    assert saved.asked_at_turn == 1


@pytest.mark.asyncio
async def test_not_in_catalog_ten_xe_may_thi_bay_danh_muc_xe_may() -> None:
    from src.agents.core.actions import NotInCatalog

    browse = FakeCatalogBrowse()
    state = _state(stage=Stage.COLLECTING, pending=Pending(kind=K.CHOICE, key="vehicle"))
    await _act(NotInCatalog(mention="Evo"), state, AgentServices(catalog_browse=browse), user_message="em muốn con evo")
    assert all(call["vehicle_type_hint"] == "ELECTRIC_MOTORBIKE" for call in browse.calls)


# ---------- đợt 8: thẻ lái thử MỘT thẻ — có vị trí thì thẻ mang vehicle_id ----------


@pytest.mark.asyncio
async def test_the_lai_thu_co_vi_tri_mang_vehicle_id_va_khong_can_vi_tri() -> None:
    from src.agents.contracts import TestDriveCardView

    class CardDrive(FakeTestDriveAnswer):
        async def answer(self, **kwargs: Any) -> TestDriveResult:
            base = await super().answer(**kwargs)
            return TestDriveResult(
                answer=base.answer,
                card=TestDriveCardView(vehicle_name=kwargs["vehicle_name"]),
                slot_options=base.slot_options,
            )

    services = AgentServices(
        test_drive=CardDrive(), catalog_browse=FakeCatalogBrowse(), conversation=FakeConversationLocation(_HANOI)
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lái thử")
    card = result.cards["test_drive_card"]
    assert card.vehicle_id == V1 and card.needs_location is False


@pytest.mark.asyncio
async def test_vehicle_qa_hoi_mot_thong_so_thi_tra_dung_cot() -> None:
    # Probe H-7 (2026-08-30): "VF 5 sạc bao lâu" nhận nguyên bảng tổng quan.
    from decimal import Decimal

    facts = VehicleFacts(
        vehicle_id=UUID(V1),
        display_name="VinFast VF 5",
        vehicle_type=VehicleType.CAR,
        starting_price_vnd=Decimal("496000000"),
        specs={"fast_charge_time_minutes": Decimal("30"), "range_km": Decimal("326.00")},
    )
    services = AgentServices(
        vehicle_overview=FakeFitOverview({"VinFast VF 5": facts}), catalog_browse=FakeCatalogBrowse()
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(VehicleQa(vehicle_id=V1, question="sạc bao lâu"), state, services)
    assert "30 phút" in result.text
    assert "tổng quan" not in result.text


@pytest.mark.asyncio
async def test_handoff_theo_yeu_cau_khach_thi_xac_nhan_khong_noi_chua_ho_tro() -> None:
    from src.agents.core.actions import Handoff

    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1,), slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Handoff(reason="requested"), state, AgentServices(catalog_browse=FakeCatalogBrowse()))
    assert "chuyển anh/chị sang tư vấn viên" in result.text
    assert "chưa hỗ trợ" not in result.text
    assert result.state_patch["stage"] is Stage.HANDED_OFF


@pytest.mark.asyncio
async def test_enqueue_hitl_kem_tong_hop_khach_cho_tvv() -> None:
    # Sếp 2026-08-31: TVV nhận mục ưu đãi phải thấy khách quan tâm xe nào, nhu
    # cầu gì, còn lăn tăn gì — trước đây snapshot=None.
    from types import SimpleNamespace

    from src.agents.core.actions import EnqueueHitl

    class FakeConv:
        async def read_transcript(self, session_id: str, customer_id: str, limit: int = 50) -> list[Any]:
            return [
                SimpleNamespace(role="USER", content="ô tô điện 500 triệu, đi làm"),
                SimpleNamespace(role="ASSISTANT", content="Với nhu cầu đi làm…"),
                SimpleNamespace(role="USER", content="giá hơi cao, có rẻ hơn không"),
                SimpleNamespace(role="USER", content="sạc ở chung cư được không"),
            ]

    services = AgentServices(catalog_browse=FakeCatalogBrowse(), conversation=FakeConv())
    state = _state(
        stage=Stage.CHOSEN,
        chosen_vehicle_id=V1,
        recommended_ids=(V1, V2),
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 500_000_000, N.PURPOSE: "đi làm", N.PASSENGER_COUNT: 4},
    )
    result = await _act(EnqueueHitl(vehicle_id=V1), state, services, run_id=uuid4(), user_message="có ưu đãi gì không")
    request = result.hitl_request
    assert request is not None and request.snapshot is not None
    snap = request.snapshot
    assert snap.considered_vehicles[0] == "VinFast VF 5"
    assert any("500" in line for line in snap.needs) and any("đi làm" in line for line in snap.needs)
    labels = {str(item.bottleneck).split(".")[-1] for item in snap.bottlenecks}
    assert {"PRICE", "CHARGING"} <= labels
    # content = NHÁP TRẢ KHÁCH, sạch chữ nội bộ; tổng hợp nằm riêng trong snapshot.
    assert "Tổng hợp khách" not in request.content and "Khách hỏi" not in request.content
    assert "ưu đãi" in request.content


@pytest.mark.asyncio
async def test_book_thanh_cong_ghi_booking_id_vao_state() -> None:
    """Đợt 9: câu kết/panel lượt sau cần biết "đã có lịch" — `Book` phải ghi `booking_id`."""

    import src.agents.core.act as act_module
    from src.agents.domain.test_drive_booking import BookingChoice

    when = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        act_module,
        "read_slot_token",
        lambda message, **_kwargs: BookingChoice(showroom="VinFast HTA", scheduled_at=when),
    )
    booked = uuid4()

    class FakeTestDrive:
        async def book(self, **_kwargs):
            return booked

    try:
        services = AgentServices(test_drive=FakeTestDrive(), catalog_browse=FakeCatalogBrowse())
        state = _state(stage=Stage.SCHEDULING, chosen_vehicle_id=V1, slots=CAR_FULL)
        result = await _act(Book(vehicle_id=V1, choice_ref="x"), state, services, user_message="x")
    finally:
        monkey.undo()
    assert result.state_patch["booking_id"] == str(booked)


@pytest.mark.asyncio
async def test_da_co_lich_thi_cau_ket_khong_moi_lai_thu_nua() -> None:
    services = AgentServices(vehicle_overview=FakeOverview("Tổng quan VF 5."), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL, booking_id=str(uuid4()))
    result = await _act(VehicleQa(vehicle_id=V1, question="màu gì"), state, services)
    assert result.text.endswith("Lịch đã xếp; anh/chị cần hỏi thêm gì về VinFast VF 5 trước ngày lái thử không?")


# ------------------------------------------------------------ đợt 9: navigate


@pytest.mark.asyncio
async def test_chot_xe_thi_navigate_sang_trang_xe_dung_slug() -> None:
    from src.agents.core.actions import TEMPLATE_CHOSEN_SUMMARY

    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, recommended_ids=(V1, V2), slots=CAR_FULL)
    result = await _act(Reply(template=TEMPLATE_CHOSEN_SUMMARY, args={"vehicle_id": V1}), state, services)
    nav = result.cards["navigate"]
    assert (nav.kind, nav.vehicle_id, nav.slug, nav.name) == ("vehicle", V1, "vf-5", "VinFast VF 5")


@pytest.mark.asyncio
async def test_tra_cuu_mot_mau_thi_navigate_sang_trang_xe() -> None:
    overview = FakeOverview("VinFast VF 5 giá niêm yết 529 triệu đồng.")
    services = AgentServices(vehicle_overview=overview, catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(Lookup(mode=LOOKUP_LOOKUP, vehicle_ids=(V1,)), state, services, user_message="VF 5 giá?")
    assert result.cards["navigate"].kind == "vehicle" and result.cards["navigate"].slug == "vf-5"


@pytest.mark.asyncio
async def test_dang_de_xuat_hay_so_sanh_thi_khong_navigate() -> None:
    services = AgentServices(compare_vehicles=FakeCompare(), catalog_browse=FakeCatalogBrowse())
    state = _state(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2), slots=CAR_FULL)
    result = await _act(Compare(vehicle_ids=(V1, V2)), state, services, user_message="so sánh")
    assert "navigate" not in result.cards


@pytest.mark.asyncio
async def test_xin_lai_thu_co_showroom_thi_navigate_ban_do() -> None:
    from src.agents.contracts import TestDriveCardView, TestDriveShowroomView

    card = TestDriveCardView(
        vehicle_name="VinFast VF 5",
        showrooms=(
            TestDriveShowroomView(
                showroom_id="sr1",
                name="VinFast HTA",
                address="1 Láng Hạ",
                distance_label="2 km",
                lat=21.01,
                lng=105.81,
                distance_km=2.0,
            ),
        ),
    )

    class WithCard(FakeTestDriveAnswer):
        async def answer(self, **kwargs) -> TestDriveResult:
            return TestDriveResult(answer="Showroom gần anh/chị: VinFast HTA.", card=card)

    services = AgentServices(
        test_drive=WithCard(), catalog_browse=FakeCatalogBrowse(), conversation=FakeConversationLocation(_HANOI)
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lái thử")
    nav = result.cards["navigate"]
    assert nav.kind == "map" and nav.vehicle_id == V1 and nav.needs_location is False
    assert (nav.center.lat, nav.center.lng) == (_HANOI["latitude"], _HANOI["longitude"])
    assert [(s.showroom_id, s.lat, s.lng, s.distance_km) for s in nav.showrooms] == [("sr1", 21.01, 105.81, 2.0)]


@pytest.mark.asyncio
async def test_xin_lai_thu_chua_biet_vi_tri_thi_navigate_ban_do_needs_location() -> None:
    services = AgentServices(
        test_drive=FakeTestDriveAnswer(),
        catalog_browse=FakeCatalogBrowse(),
        conversation=FakeConversationLocation(None),
    )
    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots=CAR_FULL)
    result = await _act(ShowroomOptions(vehicle_id=V1), state, services, user_message="đặt lái thử")
    nav = result.cards["navigate"]
    assert nav.kind == "map" and nav.needs_location is True and nav.center is None and nav.showrooms == ()


@pytest.mark.asyncio
async def test_chinh_sach_khong_nguon_thi_chuyen_that_cho_tvv_va_khong_cam() -> None:
    # Prod 2026-08-31: "thế còn bảo hành" chỉ nói mời TVV mà không tạo mục duyệt nào.
    from src.agents.core.actions import LOOKUP_POLICY, Lookup

    state = _state(stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(
        Lookup(mode=LOOKUP_POLICY),
        state,
        AgentServices(catalog_browse=FakeCatalogBrowse()),
        run_id=RUN_ID,
        user_message="thế còn bảo hành",
    )
    assert result.hitl_request is not None and "tư vấn viên" in result.hitl_request.content
    assert result.state_patch.get("stage") is Stage.OFFER_REVIEW  # bot vẫn trả lời các lượt sau
    assert "hỏi tiếp" in result.text


# ---------- bug prod 2026-08-31: pitch khẳng định xe tầm ngắn hợp đi xa ----------


def test_relax_ladder_bo_tam_chay_truoc_roi_moi_bo_ngan_sach() -> None:
    """"200 triệu + đi xa": nới ngân sách hai bậc chưa đủ thì bước kế là BỎ TẦM
    CHẠY nhưng GIỮ ngân sách — khách xem được mẫu gần túi tiền kèm câu nói thẳng
    thiếu tầm, thay vì bỏ cả hai tiêu chí một lúc trong im lặng."""

    criteria = FilterCriteria(
        vehicle_type=VehicleType.CAR, budget_max_vnd=Decimal("200000000"), required_range_km=300
    )
    steps = _relax_ladder(criteria)
    assert [code for _, code in steps] == ["budget", "budget", "range", "other"]
    dropped_range = steps[2][0]
    assert dropped_range.required_range_km is None
    assert dropped_range.budget_max_vnd is not None


@pytest.mark.asyncio
async def test_cau_dan_khong_khang_dinh_xe_tam_ngan_hop_di_xa() -> None:
    """Bug Sếp báo hai lần 2026-08-31: "Với nhu cầu đi du lịch đường dài, VinFast
    VF 2..." — VF 2 chỉ 210 km. Xe không đủ tầm thì BỎ tiền tố nhu cầu (bài của
    bộ viết giữ nguyên); xe đủ tầm (VF 5, 326 km) vẫn giữ tiền tố."""

    overview = FakeFitOverview(
        {
            "VinFast VF 2": _facts(V1, "VinFast VF 2", seat_count=4, range_km="210", price=239_000_000),
            "VinFast VF 5": _facts(V2, "VinFast VF 5", seat_count=5, range_km="326", price=480_000_000),
        }
    )
    services = _advisory_services(
        synthesis=FakeSynthesis(pitches=(_pitch(V1, "VinFast VF 2"), _pitch(V2, "VinFast VF 5"))),
        vehicle_overview=overview,
    )
    state = _state(
        stage=Stage.COLLECTING,
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 200_000_000, N.PURPOSE: "đi du lịch đường dài"},
    )
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="tư vấn giúp em")
    assert "Với nhu cầu đi du lịch đường dài, VinFast VF 2" not in result.text
    assert "VinFast VF 2 rất hợp." in result.text
    assert "Với nhu cầu đi du lịch đường dài, VinFast VF 5" in result.text


# ---------- bug prod 2026-08-31 11:52: "anh có 5 củ" nhận gợi ý ô tô 188 triệu ----------


class EmptyRetrieval:
    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        return []

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids) -> list:
        return []


class PricedByTypeCatalog:
    """Giá sàn theo LOẠI xe: xe máy điện rẻ nhất 12 triệu, ô tô rẻ nhất 188 triệu."""

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        if vehicle_type_hint == "ELECTRIC_MOTORBIKE":
            return CatalogBrowseResult(
                answer="",
                pitches=(
                    VehiclePitch(
                        vehicle_id=UUID(V1), rank=1, display_name="VinFast Evo Lite", pitch="",
                        starting_price_vnd="12000000",
                    ),
                ),
            )
        return CatalogBrowseResult(
            answer="",
            pitches=(
                VehiclePitch(
                    vehicle_id=UUID(V2), rank=1, display_name="VinFast VF 3 All New", pitch="",
                    starting_price_vnd="188000000",
                ),
            ),
        )


@pytest.mark.asyncio
async def test_ngan_sach_duoi_san_moi_loai_thi_noi_that_va_hoi_lai_thay_vi_chia_xe_gap_chuc_lan() -> None:
    """Prod 11:52: "anh có 5 củ mua xe để đi" (phiên khoá Ô TÔ) → bot chìa VF 2
    188 triệu "gần giá nhất" — gấp 37 lần túi tiền, đọc như trêu khách. Dưới
    hẳn giá sàn CẢ HAI loại thì phải nói thật giá sàn + hỏi lại loại xe và
    ngân sách trong MỘT câu, không gợi ý mẫu nào."""

    services = _advisory_services(retrieval=EmptyRetrieval(), catalog_browse=PricedByTypeCatalog())
    state = _state(stage=Stage.COLLECTING, slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 5_000_000})
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="anh có 5 củ mua xe để đi")

    assert "chưa có mẫu VinFast nào trong tầm" in result.text
    assert "12 triệu" in result.text and "188 triệu" in result.text
    assert "xe máy điện hay ô tô" in result.text
    assert "VF 3" not in result.text  # không chìa mẫu gấp chục lần túi tiền


@pytest.mark.asyncio
async def test_ngan_sach_lo_co_van_duoc_goi_y_mau_gan_gia_nhu_cu() -> None:
    """170 triệu vượt xa sàn xe máy điện → bậc "gần giá nhất" giữ nguyên hành vi."""

    services = _advisory_services(retrieval=EmptyRetrieval(), catalog_browse=PricedByTypeCatalog())
    state = _state(stage=Stage.COLLECTING, slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 170_000_000})
    result = await _act(Recommend(), state, services, run_id=RUN_ID, user_message="anh có 170 triệu")

    assert "gần nhất về giá" in result.text
    assert "VinFast VF 3 All New" in result.text


@pytest.mark.asyncio
async def test_ask_chon_mau_giu_job_qua_tang_act() -> None:
    """`act._ask` dựng lại Ask để điền nhãn — từng đánh rơi `job` nên câu "đặt
    lái thử mẫu nào" thành lại câu luồng thông số (Sếp bắt trên prod 31/08)."""

    from src.agents.core.actions import Ask as AskAction
    from src.agents.core.state import PendingKind

    services = AgentServices(catalog_browse=FakeCatalogBrowse())
    state = _state(slots={N.VEHICLE_TYPE: "CAR"})
    result = await _act(
        AskAction(key="vehicle", kind=PendingKind.CHOICE, job="đặt lái thử"), state, services
    )
    assert "chọn được mẫu" in result.text and "tư vấn" in result.text
