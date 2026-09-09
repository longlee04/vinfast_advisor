"""Lõi v2 gọi ĐÚNG chữ ký của bản cài đặt THẬT, không phải của Protocol.

Vì sao có file này: `registry.py` chỉ khai Protocol, và Protocol bị lệch so với
lớp thật mà `composition.py` cắm vào là chuyện đã xảy ra — `TestDriveServiceImpl.
answer` thêm `session_id`/`customer_id` (services/test_drive.py:202) mà Protocol
`registry.py:270` không theo. Test đơn vị dùng fake nên xanh; prod ném `TypeError`
ngay lượt lái thử đầu tiên và MỌI lượt lái thử rơi xuống câu dự phòng.

Cách kiểm: `inspect.signature(Impl.method).bind(<đúng bộ kwargs act/run_turn
truyền>)`. Bộ kwargs ở đây phải chép TAY từ `act.py`/`run_turn.py` — đọc từ code
bằng phản chiếu thì test tự đúng theo lỗi. Đổi chỗ gọi mà quên đổi file này là
test đỏ, đó là ý đồ.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from src.agents.core.state import CoreState
from src.agents.domain.values import VehicleType
from src.agents.services.candidate_tuning import CandidateTuningServiceImpl
from src.agents.services.catalog_browse import CatalogBrowseServiceImpl
from src.agents.services.compare_vehicles import CompareVehiclesServiceImpl
from src.agents.services.conversation import ConversationServiceImpl
from src.agents.services.conversation_memory import ConversationMemoryService
from src.agents.services.nearby_location import NearbyLocationServiceImpl
from src.agents.services.recommendation import DefaultRecommendationService
from src.agents.services.retrieval import RetrievalServiceImpl
from src.agents.services.slot_token import read_slot_token
from src.agents.services.snapshotting import DefaultSnapshottingService
from src.agents.services.synthesis import DefaultSynthesisService
from src.agents.services.tco_estimation import DefaultTcoEstimationService
from src.agents.services.test_drive import TestDriveServiceImpl as TestDriveImpl
from src.agents.services.vehicle_overview import DefaultVehicleOverviewService
from src.agents.services.verification import DefaultVerificationService

RUN_ID = uuid4()
VEHICLE_ID = uuid4()
WHEN = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)

#: `self` giả: chỉ để `Signature.bind` có đủ tham số vị trí đầu tiên.
SELF = object()

#: (tên chỗ gọi, hàm thật, args, kwargs) — kwargs chép từ chỗ gọi trong lõi v2.
CALLS: list[tuple[str, Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = [
    # ── act.py ────────────────────────────────────────────────────────────────
    (
        "act._lookup / act.catalog_names → catalog_browse.answer",
        CatalogBrowseServiceImpl.answer,
        (SELF,),
        {"user_message": "có xe nào", "vehicle_type_hint": "CAR"},
    ),
    (
        "act._compare → compare_vehicles.answer",
        CompareVehiclesServiceImpl.answer,
        (SELF,),
        {"user_message": "so sánh giúp em", "vehicle_names": ["VF 5", "VF 6"]},
    ),
    (
        "act._nearby → nearby_location.answer",
        NearbyLocationServiceImpl.answer,
        (SELF,),
        {"user_message": "showroom gần đây", "location_text": "Hà Nội", "assume_request": True},
    ),
    (
        "act._vehicle_qa → vehicle_overview.answer",
        DefaultVehicleOverviewService.answer,
        (SELF,),
        {"vehicle_name": "VinFast VF 5", "session_id": "s1"},
    ),
    (
        "act._recommend → retrieval.layer1",
        RetrievalServiceImpl.layer1,
        (SELF, object()),
        {},
    ),
    (
        "act._recommend → retrieval.layer2",
        RetrievalServiceImpl.layer2,
        (SELF,),
        {"utterance": "tư vấn giúp em", "vehicle_type": "CAR", "candidate_ids": [VEHICLE_ID]},
    ),
    (
        "act._recommend → snapshotting.snapshot",
        DefaultSnapshottingService.snapshot,
        (SELF,),
        {"run_id": RUN_ID, "candidate_ids": [VEHICLE_ID], "assertions": []},
    ),
    (
        "act._recommend → recommendation.recommend",
        DefaultRecommendationService.recommend,
        (SELF, RUN_ID),
        {"customer_asked_feature_codes": ["ADAS"], "preferred_trait_codes": (), "vehicle_type": "CAR"},
    ),
    (
        "act._fallback_vehicles → recommendation.compare",
        DefaultRecommendationService.compare,
        (SELF,),
        {"run_id": RUN_ID, "vehicle_ids": [VEHICLE_ID]},
    ),
    (
        "act._feature_pending → candidate_tuning.delegated_features",
        CandidateTuningServiceImpl.delegated_features,
        (SELF, [VEHICLE_ID]),
        {"vehicle_type": "CAR", "purpose": "đi làm"},
    ),
    (
        "act._pitch_text → synthesis.synthesize",
        DefaultSynthesisService.synthesize,
        (SELF,),
        {
            "run_id": RUN_ID,
            "recommendations": [],
            "tco": None,
            "budget_min_vnd": None,
            "budget_max_vnd": 900_000_000.0,
            "feature_mention_codes": ["ADAS"],
        },
    ),
    (
        "act._pitch_text → verification.verify",
        DefaultVerificationService.verify,
        (SELF,),
        {"run_id": RUN_ID, "draft_answer": "VF 5 rất hợp."},
    ),
    (
        "act._tco → tco_estimation.estimate",
        DefaultTcoEstimationService.estimate,
        (SELF,),
        {"vehicle_id": VEHICLE_ID, "daily_distance_km": 40.0, "run_id": RUN_ID, "region_code": "KHU_VUC_I"},
    ),
    (
        # Thiết kế 2026-08-31 ("giá lăn bánh với TCO là MỘT"): act._on_road_price
        # trả THẺ chi phí — gọi cùng cửa estimate như act._tco, KHÔNG còn đi
        # đường chữ `on_road_price.answer_with_pending` của lõi cũ.
        "act._on_road_price → tco_estimation.estimate",
        DefaultTcoEstimationService.estimate,
        (SELF,),
        {"vehicle_id": VEHICLE_ID, "daily_distance_km": 30.0, "run_id": RUN_ID, "region_code": "KHU_VUC_II"},
    ),
    (
        # ĐÂY là chỗ C1: thiếu `session_id`/`customer_id` thì prod ném TypeError.
        "act._showroom_options → test_drive.answer",
        TestDriveImpl.answer,
        (SELF,),
        {
            "user_message": "đặt lái thử",
            "vehicle_name": "VinFast VF 5",
            "vehicle_type": VehicleType.CAR,
            "known_location": None,
            "session_id": "s1",
            "customer_id": "c1",
        },
    ),
    (
        "act._book → test_drive.book",
        TestDriveImpl.book,
        (SELF,),
        {"customer_id": "c1", "vehicle_id": VEHICLE_ID, "showroom": "VinFast HTA", "scheduled_at": WHEN},
    ),
    (
        "act._known_location → conversation.load_user_location",
        ConversationServiceImpl.load_user_location,
        (SELF, "s1"),
        {},
    ),
    (
        "act._book → slot_token.read_slot_token",
        read_slot_token,
        ("__lichlaithu__|a|b",),
        {"session_id": "s1", "customer_id": "c1", "now": WHEN},
    ),
    # ── run_turn.py ───────────────────────────────────────────────────────────
    (
        "run_turn._open_session → conversation.open_session",
        ConversationServiceImpl.open_session,
        (SELF, "s1", "c1"),
        {},
    ),
    (
        "run_turn._load_state → conversation.load_core_state",
        ConversationServiceImpl.load_core_state,
        (SELF, "s1"),
        {},
    ),
    (
        "run_turn._project_ownership → conversation.load_handoff_state",
        ConversationServiceImpl.load_handoff_state,
        (SELF, "s1"),
        {},
    ),
    (
        "run_turn._transcript → conversation.read_transcript",
        ConversationServiceImpl.read_transcript,
        (SELF, "s1", "c1", 50),
        {},
    ),
    (
        "run_turn._create_run → conversation.create_run",
        ConversationServiceImpl.create_run,
        (SELF, "s1", {}),
        {},
    ),
    (
        "run_turn._start_memory → memory.start_turn",
        ConversationMemoryService.start_turn,
        (SELF,),
        {
            "session_id": "s1",
            "customer_id": "c1",
            "client_turn_id": uuid4(),
            "user_message": "chào em",
            "slots": {},
        },
    ),
    (
        "run_turn._commit → memory.commit_core_turn",
        ConversationMemoryService.commit_core_turn,
        (SELF,),
        {
            "lease": object(),
            "customer_id": "c1",
            "user_message": "chào em",
            "result": object(),
            "core_state": CoreState(session_id="s1"),
            "trace": object(),
            "advisor_review": None,
        },
    ),
]


@pytest.mark.parametrize("label, target, args, kwargs", CALLS, ids=[item[0] for item in CALLS])
def test_chu_ky_that_nhan_dung_bo_tham_so_loi_v2_truyen(
    label: str, target: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    try:
        inspect.signature(target).bind(*args, **kwargs)
    except TypeError as error:  # pragma: no cover - chỉ chạy khi hợp đồng lệch
        pytest.fail(f"{label}: lõi v2 truyền sai bộ tham số cho bản cài đặt thật — {error}")


def test_khong_bo_sot_service_nao_act_dang_goi() -> None:
    """Chốt số lượng: thêm một lời gọi service mới vào `act` thì phải thêm dòng.

    Không có chốt này thì file trên lặng lẽ phủ thiếu đúng cái mới thêm — mà cái
    mới thêm mới là cái chưa ai chạy thật bao giờ.
    """

    assert len(CALLS) == 25
    assert len({item[0] for item in CALLS}) == len(CALLS)


def test_decimal_khong_bao_gio_di_nguoc_vao_slot() -> None:
    """`estimate` nhận `Decimal` cho `discount_vnd` — lõi v2 KHÔNG truyền nó."""

    parameters = inspect.signature(DefaultTcoEstimationService.estimate).parameters
    assert parameters["discount_vnd"].default == Decimal("0")
