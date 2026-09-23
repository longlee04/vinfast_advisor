"""`AgentServices` — 12 use case nhóm advisory (mục 6.3), CHỈ node trong graph gọi.

Đóng băng ở Ngày 0 (§2.1/§2.2 docs/team_split.md): **không ai sửa trừ PR
contract** — đổi một chữ ký Protocol dưới đây là một PR riêng, cả 4 người
duyệt, nêu rõ ai đang phụ thuộc chữ ký cũ. Đổi thân class thật implement các
Protocol này (viết ở `services/*.py` của từng khối) là tự do.

Mỗi field mặc định `None` để `AgentServices()` không tham số vẫn dựng được
(khung graph rỗng, `tests/agents/unit/test_graph_skeleton.py`) — mỗi khối chỉ
cần truyền field mình đang test qua `composition.py`, field khác để `None`.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from src.agents.contracts import (
    CatalogBrowseResult,
    CompareVehiclesResult,
    ExtractedSlots,
    FeatureAssertion,
    FilterCriteria,
    FindNearbyLocationResult,
    QuoteGateDecision,
    Recommendation,
    TcoResult,
    TestDriveResult,
    TurnResult,
    VehicleFacts,
    VehiclePitch,
)
from src.agents.domain.bottleneck_signal import BottleneckDetectionResult
from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.conversation_memory import (
    ConversationMessage,
    TurnOutcome,
    WorkingMemoryProjection,
)
from src.agents.domain.injection_gate import InjectionJudgePrediction
from src.agents.domain.location_tool import LocationArgResolverPort
from src.agents.domain.nearby_location import LocationKind, UserLocation
from src.agents.domain.pending_intent_confirmation import ConfirmationResolution
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.quote_risk import RiskFlagPrediction
from src.agents.domain.scope import ScopeDecision
from src.agents.domain.slot_salvage import VagueJudgePrediction
from src.agents.domain.spec_tool import SpecArgResolverPort
from src.agents.domain.task_state import ActiveTask
from src.agents.domain.tco_tool import TcoArgResolverPort
from src.agents.domain.values import ScopeLabel, SlotValue, VehicleType
from src.agents.domain.vehicle_overview import VehicleOverviewResult
from src.agents.ports import (
    AgentFlagPort,
    AgentLoopPort,
    OfferSuggestionPort,
    PolicySearchPort,
    UnderstandingPort,
)
from src.agents.services.candidate_tuning import DelegatedFeatureChoice
from src.agents.services.conversation_memory import StartedMemoryTurn
from src.agents.services.nlu_pipeline import NluDecision
from src.agents.services.profile_snapshot import ProfileSnapshotService
from src.agents.services.task_context import TaskFollowupResolution
from src.agents.services.turn_handoff import TurnHandoffService


class ConversationService(Protocol):
    """A2-2: nạp/ghi phiên + slot; nguồn sự thật của state (mục 6.9).

    Khoá slot ở biên này là **chuỗi thô** (`SlotName.value`), không phải `SlotName`:
    `nodes/` bị cấm import `domain/` (mục 6.5b) nên node không dựng được enum.
    Service tự đổi chuỗi ↔ enum trước khi chạm repository.
    """

    async def load_slots(self, session_id: str, customer_id: str) -> dict[str, SlotValue]: ...

    async def load_active_offers(self, session_id: str) -> list[dict[str, object]]: ...

    async def save_turn(self, session_id: str, customer_id: str, slots: Mapping[str, SlotValue]) -> None: ...

    async def restart_advisory(self, session_id: str) -> None: ...

    async def create_run(self, session_id: str, slots: Mapping[str, SlotValue] | None = None) -> UUID: ...

    # A7-5: bộ nhớ báo giá gần nhất của phiên. Nằm cùng `ConversationService` vì
    # nó là state của PHIÊN, cùng nhóm với slot — không phải một use case mới.
    async def load_quote_decision(self, session_id: str) -> tuple[dict[str, object] | None, datetime | None]: ...

    async def save_quote_decision(
        self, session_id: str, evaluation: Mapping[str, object], sent_at: datetime
    ) -> None: ...

    # A7-10: slot đang chờ khách trả lời. `None` ở `save` nghĩa là XOÁ.
    async def load_pending_slot(self, session_id: str) -> dict[str, object] | None: ...

    async def save_pending_slot(self, session_id: str, payload: Mapping[str, object] | None) -> None: ...

    async def load_active_task(self, session_id: str) -> dict[str, object] | None: ...

    async def save_active_task(self, session_id: str, payload: Mapping[str, object] | None) -> None: ...

    # T8: transcript gần nhất cho ProfileSnapshotService. Trả các message theo
    # thứ tự ổn định; node chỉ đọc, không cần phân trang sâu.
    async def read_transcript(
        self, session_id: str, customer_id: str, limit: int = 50
    ) -> Sequence[ConversationMessage]: ...

    # Todo 8: outcome gần nhất của phiên — nguồn bằng chứng phản hồi cảm xúc.
    async def load_latest_outcome(self, conversation_id: UUID, customer_id: str) -> TurnOutcome | None: ...


class ActiveTaskServicePort(Protocol):
    """Resolve and construct follow-up-eligible operational task state."""

    def resolve(self, *, payload: Mapping[str, object] | None, user_message: str) -> TaskFollowupResolution: ...

    def completed_on_road_task(
        self,
        *,
        vehicle_id: UUID | str,
        vehicle_name: str,
        province: str,
        previous: ActiveTask | None = None,
    ) -> ActiveTask: ...

    def completed_advisory_task(
        self,
        *,
        recommendation_ids: list[UUID | str],
        previous: ActiveTask | None = None,
    ) -> ActiveTask: ...


class BottleneckDetectorService(Protocol):
    """Classify only current redacted customer quote into closed detector outcomes."""

    async def detect(self, current_server_quote: str) -> BottleneckDetectionResult: ...


class AskTrackingService(Protocol):
    """Đếm số lần đã hỏi từng slot, để bỏ qua slot khách không trả lời được.

    Tách khỏi `ConversationService` vì đây là mối quan tâm khác: phiên/slot là
    NỘI DUNG khách đã nói, còn đếm này là hành vi của agent. `None` nghĩa là tắt
    tính năng — luồng hỏi vẫn chạy y như trước, chỉ không có trần retry.
    """

    async def load_ask_counts(self, session_id: str) -> dict[str, int]: ...

    async def record_ask(self, session_id: str, slot_name: str) -> None: ...

    async def clear_ask(self, session_id: str, slot_name: str) -> None: ...


class SlotExtractionService(Protocol):
    """A2-3: LLM function calling, validate Pydantic, gộp intent (mục 6.10)."""

    async def extract(
        self,
        *,
        session_id: str,
        customer_id: str,
        vehicle_type: str | None,
        user_message: str,
        conversation_history: str | WorkingMemoryProjection = "",
        active_task: Mapping[str, object] | None = None,
    ) -> ExtractedSlots: ...

    async def consume_pending(self, session_id: str, customer_id: str) -> list[str]: ...


class ConversationMemoryServicePort(Protocol):
    """Build durable working memory around one graph invocation."""

    async def start_turn(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID | None,
        user_message: str,
        slots: dict[str, SlotValue],
        pending_features: tuple[str, ...] = (),
    ) -> StartedMemoryTurn: ...

    async def complete_turn(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID | None,
        user_message: str,
        delivered_assistant: str,
    ) -> None: ...

    async def finalize_turn(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID,
        user_message: str,
        result: TurnResult,
        slots: dict[str, SlotValue],
    ) -> TurnResult: ...

    async def fail_turn(self, *, session_id: str, client_turn_id: UUID, error_category: str) -> None: ...


class SlotPlanningService(Protocol):
    """A3-2: `next_question` — tối đa một câu hỏi, render từ template (mục 6.11).

    Nhận chuỗi thô cùng lý do như `ConversationService`: node không import `domain/`.
    Chuỗi không khớp `SlotName`/`VehicleType` nào bị bỏ qua, không raise — LLM trả
    rác không được làm chết lượt (A2-3).
    """

    def next_question(self, *, vehicle_type: str | None, known_slots: Mapping[str, SlotValue]) -> str | None: ...

    def build_criteria(self, *, vehicle_type: str, known_slots: Mapping[str, SlotValue]) -> FilterCriteria: ...


class IntentRoutingService(Protocol):
    """A4-1: resolve tên xe khách nêu (CATALOG_LOOKUP) — không gọi LLM."""

    # `user_message` optional: service dùng câu gốc để cứu mention bị bước
    # trích LLM cắt cụt. Có default nên fake cũ trong test không phải sửa.
    async def resolve_vehicle_mentions(self, mentions: Sequence[str], user_message: str = "") -> list[UUID]: ...

    async def ambiguous(self, mentions: Sequence[str], user_message: str = "") -> list[str]: ...

    async def lookup_facts(
        self, mentions: Sequence[str], user_message: str = ""
    ) -> tuple[list[VehicleFacts], list[str]]: ...


class CatalogBrowseService(Protocol):
    """A4-7: liệt kê danh mục theo LOẠI xe — không lọc nhu cầu, không gọi LLM.

    Tách khỏi `IntentRoutingService` dù cùng đọc catalog: `IntentRoutingService`
    nhận TÊN MẪU xe và trả về danh tính; service này nhận cả câu của khách và
    trả về một danh sách. Nhét vào cùng một Protocol thì `resolve_vehicle_names`
    phải hiểu được cả tên loại lẫn tên mẫu, và đó chính là chỗ bug gốc đã sinh ra.
    """

    async def answer(
        self, *, user_message: str, vehicle_type_hint: str | None = None
    ) -> CatalogBrowseResult | None: ...


class CompareVehiclesService(Protocol):
    """[COMPARE_VEHICLES] Bảng so sánh 2–3 mẫu xe khách nêu đích danh."""

    async def answer(self, *, user_message: str, vehicle_names: Sequence[str]) -> CompareVehiclesResult | None: ...


class NearbyLocationService(Protocol):
    """[FIND_NEARBY_LOCATION] Địa điểm VinFast gần vị trí khách, kèm deep link."""

    async def answer(
        self,
        *,
        user_message: str,
        known_location: UserLocation | None = None,
        location_text: str | None = None,
        location_kinds: Sequence[LocationKind] = (),
        assume_request: bool = False,
    ) -> FindNearbyLocationResult | None: ...


class TestDriveService(Protocol):
    """[TEST_DRIVE] Gợi ý showroom gần + khung giờ trống cho đặt lịch lái thử."""

    async def answer(
        self,
        *,
        user_message: str,
        vehicle_name: str,
        vehicle_type: VehicleType,
        known_location: UserLocation | None,
    ) -> TestDriveResult: ...

    async def book(
        self, *, customer_id: str, vehicle_id: UUID, showroom: str, scheduled_at: datetime
    ) -> UUID | None: ...


class VehicleOverviewService(Protocol):
    """Build a structured, evidence-backed overview for one vehicle mention."""

    async def answer(self, *, vehicle_name: str, session_id: str) -> VehicleOverviewResult: ...


class VehicleMediaService(Protocol):
    """Ảnh catalog cho card đề xuất.

    KHÔNG nằm trong run snapshot: ảnh không phải khẳng định sự thật như giá hay
    tầm hoạt động, nên đọc thẳng catalog lúc serialize là đúng ranh giới.
    """

    async def image_urls(self, vehicle_ids: Sequence[UUID]) -> dict[UUID, str]: ...


class VehicleNameResolverService(Protocol):
    """Tên xe khách gõ → `vehicle_id`.

    Tồn tại vì `chain` cần `vehicle_id` ở hai chỗ NGOÀI pipeline đề xuất — đặt
    lịch lái thử và tính chi phí cho mẫu khách vừa chốt — mà cả hai lượt đó đều
    không chạy Lớp 1 nên không có `candidates` để tra.

    Không tự khớp tên trong `chain`: catalog đã có bộ xử lý viết tắt và sai chính
    tả, và một bản đọc tên thứ hai là chỗ hai bên lệch nhau âm thầm.
    """

    async def resolve_vehicle_names(self, mentions: Sequence[str]) -> list[Any]: ...


class RetrievalService(Protocol):
    """A1-2/3/6/7: điều phối Lớp 1 → Lớp 2, áp `pending_feature_mentions`."""

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]: ...

    async def layer2(
        self, *, utterance: str, vehicle_type: str, candidate_ids: Sequence[UUID]
    ) -> list[FeatureAssertion]: ...


class CandidateTuningService(Protocol):
    """A4-3: nới ngân sách tối đa 2 lần, thu hẹp bằng 1 slot lọc mạnh nhất."""

    def relax(self, criteria: FilterCriteria, relax_count: int) -> FilterCriteria: ...

    async def narrow_question(
        self,
        candidate_ids: Sequence[UUID],
        *,
        vehicle_type: str | None = None,
        purpose: SlotValue | None = None,
        purpose_bucket_hint: str | None = None,
        user_message: str = "",
        force_full_list: bool = False,
    ) -> str | None: ...

    async def delegated_features(
        self,
        candidate_ids: Sequence[UUID],
        *,
        vehicle_type: str | None = None,
        purpose: SlotValue | None = None,
        purpose_bucket_hint: str | None = None,
    ) -> DelegatedFeatureChoice | None: ...


class SnapshottingService(Protocol):
    """A5-2: ghi `run_snapshots` bất biến — mọi số về sau đọc từ đây, không query lại catalog."""

    async def snapshot(
        self, *, run_id: UUID, candidate_ids: Sequence[UUID], assertions: Sequence[FeatureAssertion]
    ) -> None: ...


class RecommendationService(Protocol):
    """A5-3/4/7: scoring + so sánh + giới thiệu feature theo nhu cầu, đọc từ snapshot."""

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes: Collection[str] = (),
        preferred_trait_codes: Collection[str] = (),
    ) -> list[Recommendation]: ...


class TcoEstimationService(Protocol):
    """A5-5: `vinfast_tco_v1`, `Decimal` half-up, `TCO_UNAVAILABLE` khi thiếu dữ liệu.

    `region_code` KHÔNG có mặc định trong chữ ký: lệ phí biển số ô tô chênh 100
    lần giữa hai khu vực (140.000đ và 14.000.000đ), nên một mặc định lặng lẽ ở
    tầng protocol là một con số sai gửi cho khách. Người gọi phải nói ra mình
    đang tính cho khu vực nào, kể cả khi câu trả lời là "chưa biết".
    """

    async def estimate(
        self,
        *,
        vehicle_id: UUID,
        daily_distance_km: float | None,
        run_id: UUID | None = None,
        region_code: str | None = None,
        #: Tiền ưu đãi trừ vào GIÁ XE (Sếp 2026-08-27). Mặc định 0 nên mọi
        #: lời gọi cũ không đổi một đồng nào.
        discount_vnd: Decimal = Decimal("0"),
    ) -> TcoResult: ...


class SynthesisService(Protocol):
    """A5-6: prompt chỉ từ snapshot, LLM không viết chữ số — mỗi xe MỘT đoạn riêng."""

    async def synthesize(
        self,
        *,
        run_id: UUID,
        recommendations: Sequence[Recommendation],
        tco: TcoResult | None,
        customer_wording: Sequence[str] = (),
        budget_min_vnd: float | None = None,
        budget_max_vnd: float | None = None,
        feature_mention_codes: Sequence[str] = (),
    ) -> Sequence[VehiclePitch]: ...


class VerificationService(Protocol):
    """A6-1: guardrail hậu-synthesis — đối chiếu số với snapshot, retry tối đa 2 lần."""

    async def verify(self, *, run_id: UUID, draft_answer: str) -> bool: ...


class ScopeClassifierService(Protocol):
    """A6-2: gán nhãn IN_SCOPE/MISSING_DATA/OUT_OF_SCOPE, ghi `out_of_scope_log`."""

    async def classify(self, *, user_message: str) -> ScopeLabel: ...

    # Bổ sung (không đổi chữ ký `classify` cũ, cùng PR contract với Task 7):
    # node cần câu chữ trả khách nhưng bị cấm import `domain/` (mục 6.5b) nên
    # không tự dựng được `ScopeDecision` — service trả sẵn bản dựng đầy đủ.
    async def classify_with_guidance(
        self,
        *,
        user_message: str,
        canonical: CanonicalText,
        conversation_context: str = "",
        advisory_context: bool = False,
    ) -> ScopeDecision: ...

    async def decide_from_label(
        self,
        *,
        raw_label: ScopeLabel | str,
        user_message: str,
        canonical: CanonicalText,
        advisory_context: bool = False,
    ) -> ScopeDecision: ...


class ModerationService(Protocol):
    """Safety classification that runs before task resume and graph execution."""

    async def is_blocked(self, *, user_message: str, canonical: CanonicalText | None = None) -> bool: ...


class InjectionJudgePort(Protocol):
    """Lớp hai chống tiêm nhiễm (J1): bắt paraphrase mà blocklist regex bỏ sót.

    Fail-open về `InjectionJudgePrediction(False, 0.0, reason)` khi lỗi — nơi
    gọi dùng `merge_injection_verdict` để chốt, regex vẫn là đáy.
    """

    async def judge(self, user_message: str) -> InjectionJudgePrediction: ...


class RiskFlagJudgePort(Protocol):
    """Lớp hai cho bốn cờ rủi ro báo giá (J2): soát nội dung sắp gửi khách.

    Fail-open về `RiskFlagPrediction` toàn cờ `False` khi lỗi — nơi gọi dùng
    `merge_risk_flags` (chỉ OR) để chốt, regex vẫn là đáy.
    """

    async def judge(self, *, user_message: str, draft_answer: str | None) -> RiskFlagPrediction: ...


class VagueAnswerJudgePort(Protocol):
    """Lớp hai cho câu trả lời mơ hồ (J3): bắt câu né giá trị regex bỏ sót.

    Fail-open về `VagueJudgePrediction(False, 0.0, reason)` khi lỗi — nơi gọi
    dùng `merge_vague_verdict` để chốt, regex vẫn là đáy.
    """

    async def judge(self, *, user_message: str, last_question: str) -> VagueJudgePrediction: ...


class PendingSlotService(Protocol):
    """A7-10: nối câu trả lời ngắn vào câu hỏi slot bot vừa đặt."""

    def resolve(
        self,
        *,
        payload: Mapping[str, object] | None,
        user_message: str,
        now: datetime | None = None,
    ) -> object: ...


class NluPipelineService(Protocol):
    """Bốn lớp nhận diện ý định, chạy TRƯỚC bước trích slot.

    Trả `NluDecision` có kiểu thật, không phải `object`: node đọc bảy thuộc tính
    của nó, và với `object` thì mọi lần đọc sai tên thuộc tính chỉ lộ ra lúc
    chạy. Import kiểu của tầng service vào Protocol là cách `ConversationMemory
    ServicePort` (`StartedMemoryTurn`) và `ActiveTaskServicePort`
    (`TaskFollowupResolution`) đang làm.
    """

    async def recognize(
        self,
        *,
        user_message: str,
        pending_slot: str | None = None,
        pending_intent: str | None = None,
        handoff_active: bool = False,
        known_slots: Mapping[str, SlotValue] | None = None,
    ) -> NluDecision: ...


class PendingIntentConfirmationService(Protocol):
    """Tiêu thụ câu trả lời của khách cho một câu xác nhận ý định (Lớp 4).

    Tách khỏi `PendingSlotService` vì hai bản ghi khác hẳn ngữ nghĩa — xem
    docstring `domain/pending_intent_confirmation.py`.
    """

    def resolve(
        self,
        *,
        payload: Mapping[str, object] | None,
        user_message: str,
        now: datetime | None = None,
    ) -> ConfirmationResolution: ...


class OnRoadPriceService(Protocol):
    """A7-9: giá lăn bánh — tính deterministic từ biểu phí đã công bố.

    Chạy tự động, không qua HITL khi đủ xe và tỉnh vì công thức chỉ dùng biểu
    phí đã công bố. Thiếu tỉnh thì HỎI LẠI chứ không đoán.
    """

    async def answer(self, *, user_message: str, vehicle_id: UUID | None, vehicle_name: str) -> str | None: ...

    async def answer_with_pending(
        self,
        *,
        user_message: str,
        canonical: CanonicalText,
        vehicle_id: UUID | None,
        vehicle_name: str,
    ) -> tuple[str | None, PendingSlotRequest | None]:
        """Câu trả lời KÈM bản ghi chờ khi còn thiếu tỉnh.

        Khai ở đây vì `chain` và `nodes/route_intent` đều gọi nó. Thiếu dòng này
        thì hợp đồng chỉ tồn tại trong bản cài đặt thật: một test double viết
        đúng Protocol vẫn nổ `AttributeError`, và bộ kiểm kiểu không nói được gì.
        """
        ...


class QuoteGateService(Protocol):
    """A7-4: quyết định một lượt có phải chờ tư vấn viên duyệt không (PRD 5.6).

    Cùng nhóm advisory và cùng lý do với `hitl`: chỉ graph mới biết lượt này đang
    sắp gửi gì cho khách, nên quyết định chặn/không chặn không đặt được ở route
    HTTP. Quyết định là rule-based (`domain/quote_risk.py`), KHÔNG gọi LLM.
    """

    async def evaluate(
        self,
        *,
        session_id: str,
        run_id: UUID | None = None,
        user_message: str,
        draft_answer: str | None = None,
        lookup_facts: Sequence[VehicleFacts] = (),
        unresolved_mentions: Sequence[str] = (),
        rendered_answer: str | None = None,
        slots_before: Mapping[str, object] | None = None,
        slots_after: Mapping[str, object] | None = None,
        last_quote_evaluation: Mapping[str, object] | None = None,
        recommendation_count: int = 0,
        facts_verified: bool | None = None,
        active_offers: Sequence[Mapping[str, object]] = (),
    ) -> QuoteGateDecision: ...


class FeatureFitSource(Protocol):
    """Đọc `feature_need_tags` cho các xe vừa đề xuất / vừa tra cứu."""

    async def load(self, vehicle_ids: Sequence[UUID], need_tags: Sequence[str]) -> Mapping[UUID, Sequence[Any]]: ...


@dataclass(frozen=True)
class AgentServices:
    """Tập use case mà node được phép gọi (mục 6.3).

    Chỉ gồm nhóm advisory — nhóm operations không bao giờ vào graph.
    `composition.py` là nơi DUY NHẤT dựng AgentServices; nhờ vậy test graph chỉ
    cần một AgentServices toàn fake, không DB, không LLM.
    """

    conversation: ConversationService | None = None
    bottleneck_detector: BottleneckDetectorService | None = None
    ask_tracking: AskTrackingService | None = None
    memory: ConversationMemoryServicePort | None = None
    slot_extraction: SlotExtractionService | None = None
    slot_planning: SlotPlanningService | None = None
    intent_routing: IntentRoutingService | None = None
    catalog_browse: CatalogBrowseService | None = None
    # Field MỚI mặc định `None`: thêm field không đổi chữ ký nào đang có, cùng
    # cách `nlu_pipeline`/`on_road_price` đã được thêm.
    compare_vehicles: CompareVehiclesService | None = None
    nearby_location: NearbyLocationService | None = None
    test_drive: TestDriveService | None = None
    vehicle_overview: VehicleOverviewService | None = None
    vehicle_media: VehicleMediaService | None = None
    #: Tra `vehicle_id` từ tên xe cho các lượt NGOÀI pipeline đề xuất.
    #:
    #: Trước 2026-08-26 `chain._vehicle_id_for` đọc `services.catalog` — một field
    #: KHÔNG TỒN TẠI, nên `getattr` luôn trả `None` và bước đặt lịch lái thử không
    #: bao giờ tra nổi chiếc xe khách vừa chọn. Lỗi im lặng vì cả đường đó chỉ
    #: chạy ở cuối luồng, chỗ chưa lần nào đi hết trên prod.
    vehicle_names: VehicleNameResolverService | None = None
    retrieval: RetrievalService | None = None
    candidate_tuning: CandidateTuningService | None = None
    snapshotting: SnapshottingService | None = None
    recommendation: RecommendationService | None = None
    #: Cặp (tính năng xe có thật, nhu cầu) + câu lợi ích đã duyệt — `domain/feature_fit`.
    feature_fit: FeatureFitSource | None = None
    tco_estimation: TcoEstimationService | None = None
    #: [Tool-calling] LLM cầm tool `tinh_chi_phi` tự chọn km/tỉnh từ câu khách
    #: khi slot còn thiếu — đường PHỤ của `_tco`, `None` thì lõi y nguyên.
    tco_arg_resolver: TcoArgResolverPort | None = None
    #: [Tool-calling] LLM cầm tool `tim_diem_dich_vu` chọn loại điểm/khu vực
    #: khi bộ dò từ khoá chịu thua — đường PHỤ của `_nearby`, `None` thì y nguyên.
    location_arg_resolver: LocationArgResolverPort | None = None
    #: [Tool-calling] LLM xếp nhóm thông số cho câu hỏi tự do — đường PHỤ của `_vehicle_qa`.
    spec_arg_resolver: SpecArgResolverPort | None = None
    synthesis: SynthesisService | None = None
    verification: VerificationService | None = None
    #: Tìm đoạn tài liệu chính sách (BM25 + vector) cho câu hỏi bảo hành/trả góp.
    #:
    #: `None` là trạng thái THẬT hôm nay: `SqlAlchemyPolicySearchAdapter` đã có
    #: nhưng `composition` chưa cắm và prod chưa có tài liệu nào. Lõi v2 đọc field
    #: này ở `core/act._policy_lookup`; `None` thì nó nói thật là chưa có tài liệu
    #: chứ KHÔNG rơi về `catalog_browse` (trả danh mục xe cho câu hỏi bảo hành).
    policy_search: PolicySearchPort | None = None
    moderation: ModerationService | None = None
    injection_judge: InjectionJudgePort | None = None
    risk_flag_judge: RiskFlagJudgePort | None = None
    vague_answer_judge: VagueAnswerJudgePort | None = None
    scope_classifier: ScopeClassifierService | None = None
    pending_slot: PendingSlotService | None = None
    # Bốn lớp nhận diện ý định. Field MỚI mặc định `None` — thêm field không đổi
    # chữ ký nào đang có, nên không phải PR contract (§2.2 docs/team_split.md);
    # cùng cách `pending_slot`/`on_road_price`/`quote_gate` đã được thêm ở A7.
    nlu_pipeline: NluPipelineService | None = None
    pending_intent_confirmation: PendingIntentConfirmationService | None = None
    on_road_price: OnRoadPriceService | None = None
    task_context: ActiveTaskServicePort | None = None
    quote_gate: QuoteGateService | None = None
    #: Điểm DUY NHẤT ghi một lần chuyển người xuống database, trong một giao dịch.
    #: Chốt trước LLM, chốt ngữ nghĩa và guardrail cạn lượt đều đi qua đây.
    turn_handoff: TurnHandoffService | None = None
    profile_snapshot_service: ProfileSnapshotService | None = None
    offer_suggestion_service: OfferSuggestionPort | None = None
    #: [Lõi v2] Một cửa LLM hiểu ý (spec 2026-08-29 mục 5). Field MỚI mặc định
    #: `None` — không cắm thì không đường nào chạm tới, lõi cũ y nguyên. Bước 3
    #: (`core/run_turn.py`) mới là nơi đầu tiên đọc field này.
    understanding: UnderstandingPort | None = None
    #: [Agent] Cờ động `agent_feature_flags` (plan agent-migration Bước 3). Field
    #: MỚI mặc định `None` — `None` = TẮT, không đường nào đọc tới khi chưa cắm.
    agent_flag: AgentFlagPort | None = None
    #: [Agent] Vòng ReAct chỉ-đọc cho hai móc ngõ cụt. `None` = không móc nào
    #: chạy, lõi tất định y nguyên.
    agent_loop: AgentLoopPort | None = None
