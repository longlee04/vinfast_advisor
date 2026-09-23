"""Composition root cho module `agents` (mục 6.0): settings → adapters → services → build_graph().

Đây là nơi DUY NHẤT dựng `AgentServices`. Nhờ vậy test graph chỉ cần một
`AgentServices` toàn fake, không DB, không LLM.

Service nào chưa có adapter thật thì để `None` — node tự bỏ qua. Đó là cách
Khối 2 chạy được endpoint trước khi `adapters/llm.py` tồn tại, thay vì dựng một
LLM giả trong production và trả lời bịa.
"""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from typing import cast

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.agents.adapters.agent_flag_repository import SqlAlchemyAgentFlagAdapter
from src.agents.adapters.agent_loop_llm import OpenAIAgentLoop
from src.agents.adapters.bottleneck_detector import OpenAIBottleneckDetector
from src.agents.adapters.bottleneck_signal_repository import (
    SqlAlchemyBottleneckSignalRepository,
)
from src.agents.adapters.budgeted_llm import (
    BudgetedBottleneckDetector,
    MeteredLLM,
    MeteredWriter,
)
from src.agents.adapters.catalog_reader import CatalogReadAdapter
from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationMemoryRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyTurnOutcomeRepository,
)
from src.agents.adapters.conversation_repository import (
    SqlAlchemyMessageRepository,
    SqlAlchemyPendingFeatureMentionRepository,
    SqlAlchemySessionRepository,
)
from src.agents.adapters.embedding import OpenAIEmbeddingAdapter
from src.agents.adapters.feature_fit_source import SqlAlchemyFeatureFitSource
from src.agents.adapters.feature_vocabulary import SqlAlchemyFeatureVocabularyAdapter
from src.agents.adapters.injection_judge import OpenAIInjectionJudge
from src.agents.adapters.llm import OpenAIChatAdapter
from src.agents.adapters.location_tool_llm import OpenAILocationArgResolver
from src.agents.adapters.moderation import OpenAIModerationAdapter
from src.agents.adapters.nearby_location_source import (
    LocationsGeocoder,
    LocationsNearbySource,
)
from src.agents.adapters.offer_policy_source import (
    OfferAdjustmentLogDataSource,
    OfferPolicyDataSource,
)
from src.agents.adapters.offer_suggestion_source import OfferSuggestionDataSource
from src.agents.adapters.policy_search import SqlAlchemyPolicySearchAdapter
from src.agents.adapters.post_pitch_branch_classifier import OpenAIPostPitchBranchClassifier
from src.agents.adapters.quote_audit import BackgroundQuoteAuditSink
from src.agents.adapters.rate_limiter import PostgresTurnRateLimiter
from src.agents.adapters.recommendation_source import (
    SqlAlchemyFeatureIntroductionSource,
    SqlAlchemyRecommendationDataSource,
)
from src.agents.adapters.repositories import (
    SqlAlchemyReviewQueueRepository,
    SqlAlchemyTurnTraceRepository,
    build_agent_transaction,
)
from src.agents.adapters.rewrite_source import LlmTextRewriter
from src.agents.adapters.risk_flag_judge import OpenAIRiskFlagJudge
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.adapters.sales_opportunity_source import SalesOpportunityDataSource
from src.agents.adapters.scope_source import (
    ContextVarScopeSessionContext,
    LlmScopeClassifier,
)
from src.agents.adapters.session_offer_repository import SqlAlchemySessionOfferRepository
from src.agents.adapters.snapshot_source import SqlAlchemyCatalogSnapshotSource
from src.agents.adapters.spec_tool_llm import OpenAISpecArgResolver
from src.agents.adapters.summary_llm import OpenAIConversationSummarizer
from src.agents.adapters.synthesis_source import SqlAlchemySynthesisDataSource
from src.agents.adapters.tco_source import ProductTcoDataSource
from src.agents.adapters.tco_tool_llm import OpenAITcoArgResolver
from src.agents.adapters.understanding_llm import OpenAIUnderstander
from src.agents.adapters.unit_of_work import (
    AgentUnitOfWork,
    SqlAlchemyQuoteAuditUnitOfWork,
    SqlAlchemyScopeLogUnitOfWork,
)
from src.agents.adapters.vague_answer_judge import OpenAIVagueAnswerJudge
from src.agents.adapters.vehicle_image import build_minio_vehicle_image_source
from src.agents.adapters.vehicle_overview_source import SqlAlchemyVehicleOverviewSource
from src.agents.adapters.verification_source import SqlAlchemyVerificationDataSource
from src.agents.core.repository import CoreStateRepository
from src.agents.domain.entity_catalog import default_catalog
from src.agents.domain.fuzzy_slot_extractors import (
    FUZZY_FALLBACK_EXTRACTORS,
    compare_targets_extractor,
    test_drive_vehicle_extractor,
)
from src.agents.domain.nearby_location import (
    LOCATION_KIND_SLOT,
    USER_LOCATION_SLOT,
    location_kind_from,
    location_text_from,
)
from src.agents.domain.on_road_pending import ON_ROAD_VEHICLE_SLOT
from src.agents.domain.test_drive import TEST_DRIVE_VEHICLE_SLOT
from src.agents.domain.vehicle_comparison import COMPARE_TARGETS_SLOT
from src.agents.ports import (
    BottleneckSignalRepository,
    ClockPort,
    ConversationMemoryRepository,
    ConversationRepository,
    CoreStateRepositoryPort,
    EmbeddingPort,
    MessageRepository,
    PendingFeatureMentionPort,
    ReviewQueueRepository,
    RunRepository,
    SessionOfferRepository,
    SessionRepository,
    TurnOutcomeRepository,
    TurnTraceRepository,
    UnitOfWorkPort,
)
from src.agents.prompts.comparison_replies import (
    COMPARE_TARGETS_GIVE_UP,
    compare_targets_retry_question,
)
from src.agents.prompts.nearby_location_replies import (
    ASK_LOCATION_KIND_RETRY,
    ASK_LOCATION_RETRY,
    LOCATION_GIVE_UP,
    LOCATION_KIND_GIVE_UP,
)
from src.agents.prompts.pricing_reply import MISSING_PROVINCE_QUESTION
from src.agents.services.candidate_tuning import (
    CandidateTuningServiceImpl,
    CatalogDifferentiator,
)
from src.agents.services.catalog_browse import CatalogBrowseServiceImpl
from src.agents.services.compare_vehicles import CompareVehiclesServiceImpl
from src.agents.services.conversation import (
    AskTrackingServiceImpl,
    ConversationLifecycleService,
    ConversationServiceImpl,
)
from src.agents.services.conversation_memory import ConversationMemoryService
from src.agents.services.intent_routing import IntentRoutingServiceImpl
from src.agents.services.nearby_location import NearbyLocationServiceImpl
from src.agents.services.nlu_pipeline import (
    NluPipelineConfig,
    NluPipelineServiceImpl,
    build_known_tokens,
)
from src.agents.services.on_road_price import OnRoadPriceServiceImpl
from src.agents.services.operations.analytics import AnalyticsOperations
from src.agents.services.operations.assignment import AssignmentOperations
from src.agents.services.operations.booking import BookingOperations
from src.agents.services.operations.bottleneck_signal import BottleneckSignalOperations
from src.agents.services.operations.comparison_image import (
    ComparisonImageStore,
    default_comparison_image_dir,
)
from src.agents.services.operations.history import HistoryOperations
from src.agents.services.operations.notices import NoticeOperations
from src.agents.services.operations.review import ReviewOperations
from src.agents.services.operations.turn_events import InMemoryTurnEventBroker
from src.agents.services.operations.turn_trace import TurnTraceOperations
from src.agents.services.pending_intent_confirmation import (
    PendingIntentConfirmationServiceImpl,
)
from src.agents.services.pending_slot import (
    DEFAULT_EXTRACTORS,
    PendingSlotServiceImpl,
    message_only_extractor,
)
from src.agents.services.profile_snapshot import ProfileSnapshotService
from src.agents.services.quote_gate import QuoteGateConfig, QuoteGateServiceImpl
from src.agents.services.recommendation import DefaultRecommendationService
from src.agents.services.registry import AgentServices
from src.agents.services.retrieval import RetrievalServiceImpl
from src.agents.services.rewrite import RewriteServiceImpl
from src.agents.services.sales_opportunity import SalesOpportunityService
from src.agents.services.scope_classifier import DefaultScopeClassifierService
from src.agents.services.slot_extraction import SlotExtractionServiceImpl
from src.agents.services.slot_planning import SlotPlanningServiceImpl
from src.agents.services.snapshotting import DefaultSnapshottingService
from src.agents.services.synthesis import DefaultSynthesisService
from src.agents.services.task_context import ActiveTaskService
from src.agents.services.tco_estimation import DefaultTcoEstimationService
from src.agents.services.test_drive import BookingUnitOfWorkSlotCounter, TestDriveServiceImpl
from src.agents.services.turn_handoff import TurnHandoffService
from src.agents.services.vehicle_overview import DefaultVehicleOverviewService
from src.agents.services.verification import DefaultVerificationService
from src.config import get_settings
from src.locations.infrastructure.geocoding import CachedGeocoder
from src.products.application.offer_adjustment_service import OfferAdjustmentService


@dataclass(frozen=True, slots=True)
class AgentOperations:
    """Năm use case operations — chỉ route HTTP gọi, không đi qua graph."""

    review: ReviewOperations
    bottleneck_signals: BottleneckSignalOperations
    booking: BookingOperations
    history: HistoryOperations
    notices: NoticeOperations
    analytics: AnalyticsOperations
    conversations: ConversationLifecycleService
    assignments: AssignmentOperations
    sales_opportunity: SalesOpportunityService
    turn_traces: TurnTraceOperations


@dataclass(frozen=True, slots=True)
class ConversationTransaction:
    """Bó repository Khối 2 trong một transaction (mục 6.4).

    Hẹp hơn `SqlAlchemyAgentTransaction` của Khối 4, nhưng phải phủ ĐỦ mọi
    repository mà `ConversationMemoryService.finalize_turn` chạm tới — nó là điểm
    ghi cuối của một lượt, và bó này được `cast` sang `UnitOfWorkPort` nên trình
    kiểm kiểu KHÔNG bắt được thiếu sót; chỉ runtime mới nổ, và chỉ ở đúng nhánh
    hiếm (lượt có tín hiệu nút thắt, lượt vào hàng duyệt).

    `review_queue` nằm đây để mục duyệt của tư vấn viên được ghi TRONG CÙNG
    transaction với outcome của lượt. Ghi ở hai transaction rời để lại mục duyệt
    mồ côi khi bước sau hỏng: tư vấn viên thấy việc, khách không có lượt nào ứng
    với nó.
    """

    sessions: SessionRepository
    pending_mentions: PendingFeatureMentionPort
    memory: ConversationMemoryRepository
    conversations: ConversationRepository
    outcomes: TurnOutcomeRepository
    runs: RunRepository
    messages: MessageRepository
    review_queue: ReviewQueueRepository
    bottleneck_signals: BottleneckSignalRepository
    session_offers: SessionOfferRepository
    #: Vệt quyết định (2026-08-26). Thêm vào bó Khối 4 mà quên bó này thì
    #: `transaction.turn_traces` ném `AttributeError` mỗi lượt, hook nuốt lỗi
    #: đúng như thiết kế, và bảng vệt rỗng suốt trong im lặng — đã dính thật một
    #: lần. `tests/agents/unit/test_conversation_transaction_bundle.py` canh chỗ này.
    turn_traces: TurnTraceRepository
    #: Trạng thái lõi v2 (spec mục 4/8). Cùng bẫy với `turn_traces` ở trên: có ở
    #: `SqlAlchemyAgentTransaction` (bó Khối 4) không có nghĩa là có ở đây — bó
    #: Khối 2 này mới là bó `ConversationMemoryService.commit_core_turn` và
    #: `ConversationServiceImpl.core_state_exists`/`load_core_state` thật sự chạy
    #: trên. Thiếu trường này thì `transaction.core_state` ném `AttributeError`
    #: mỗi lượt lõi v2, và `core/flag.py:use_core_v2` nuốt lỗi rồi luôn rơi về
    #: lõi cũ — đã dính thật, xem `tests/agents/integration/test_core_run_turn.py`.
    core_state: CoreStateRepositoryPort


def _conversation_transaction(session: AsyncSession, clock: ClockPort) -> ConversationTransaction:
    return ConversationTransaction(
        sessions=SqlAlchemySessionRepository(session, clock),
        pending_mentions=SqlAlchemyPendingFeatureMentionRepository(session, clock),
        memory=SqlAlchemyConversationMemoryRepository(session, clock),
        conversations=SqlAlchemyConversationRepository(session, clock),
        outcomes=SqlAlchemyTurnOutcomeRepository(session, clock),
        runs=SqlAlchemyRunRepository(session, clock),
        messages=SqlAlchemyMessageRepository(session, clock),
        review_queue=SqlAlchemyReviewQueueRepository(session, clock),
        bottleneck_signals=SqlAlchemyBottleneckSignalRepository(session, clock),
        session_offers=SqlAlchemySessionOfferRepository(session, clock),
        turn_traces=SqlAlchemyTurnTraceRepository(session, clock),
        core_state=CoreStateRepository(session),
    )


def agent_database_url() -> str:
    """Cùng database vật lý với auth/document/product, khác version table."""

    return os.environ.get("AGENT_DATABASE_URL", os.environ.get("AUTH_DATABASE_URL", ""))


def create_agent_services(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    embedding: EmbeddingPort | None = None,
) -> AgentServices:
    """Dựng service từ một `async_sessionmaker` rời — dùng cho test tích hợp Lớp 1/Lớp 2."""

    if session_factory is None:
        return AgentServices()
    emb_port = embedding or OpenAIEmbeddingAdapter()
    return AgentServices(
        retrieval=RetrievalServiceImpl(session_factory=session_factory, embedding=emb_port),
    )


def build_agent(
    services: AgentServices | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    embedding: EmbeddingPort | None = None,
):
    """Lắp graph từ một tập service đã dựng sẵn."""

    agent_services = services or create_agent_services(session_factory=session_factory, embedding=embedding)
    # Lõi v1 (LangGraph) đã xoá 2026-08-31 — v2 không đi qua graph;
    # giữ hàm để chữ ký `run_turn(graph, ...)` không đổi ở ba route.
    del agent_services
    return None


class AgentComposition:
    """Vòng đời tài nguyên của module `agents`, khởi tạo một lần ở `lifespan`.

    `AGENT_ENABLED=false` hoặc thiếu DB URL → `services` rỗng và `graph` vẫn dựng
    được: endpoint trả câu hỏi slot đầu tiên thay vì 500. Không im lặng bịa dữ liệu.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url if database_url is not None else agent_database_url()
        self._engine: AsyncEngine | None = None
        self._services = AgentServices()
        self._operations: AgentOperations | None = None
        self._broker: InMemoryTurnEventBroker | None = None
        self._audit_sink: BackgroundQuoteAuditSink | None = None
        #: [T7a] Chống lạm dụng ở cửa API. KHÔNG đặt trong `AgentServices`: đó là
        #: nơi của use case tư vấn, còn đây là hạ tầng của endpoint — biên ấy do
        #: `test_graph_boundary` cưỡng chế.
        self._rate_limiter: PostgresTurnRateLimiter | None = None
        self._graph = None  # lõi v1 (LangGraph) đã xoá — xem chain.py

    @property
    def services(self) -> AgentServices:
        return self._services

    @property
    def graph(self):
        return self._graph

    @property
    def operations(self) -> AgentOperations | None:
        """Return HTTP operations after database-backed composition starts."""
        return self._operations

    @property
    def broker(self) -> InMemoryTurnEventBroker | None:
        """Return review event broker after database-backed composition starts."""
        return self._broker

    @property
    def rate_limiter(self) -> PostgresTurnRateLimiter | None:
        """Bộ đếm chống spam `/agent/turn`; `None` khi chưa có database."""
        return self._rate_limiter

    async def start(self) -> None:
        """Mở engine, dựng adapter thật, lắp lại graph trên service thật."""

        if not self._database_url:
            return
        self._engine = create_async_engine(self._database_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._rate_limiter = PostgresTurnRateLimiter.from_session_factory(session_factory)
        clock = SystemClock()
        unit_of_work = AgentUnitOfWork(session_factory, lambda session: _conversation_transaction(session, clock))
        catalog = CatalogReadAdapter(session_factory)
        vocabulary = SqlAlchemyFeatureVocabularyAdapter(session_factory)
        # Ngân sách bọc TẠI ĐÂY vì đây là chỗ duy nhất biết mỗi lần gọi thuộc
        # việc bắt buộc hay tuỳ chọn: synthesis, câu dẫn tìm địa điểm và tóm tắt
        # bảng so sánh đều gọi cùng một `synthesize(prompt=...)`, nhìn method là
        # không phân biệt được.
        raw_llm = OpenAIChatAdapter()
        raw_fallback_llm = OpenAIChatAdapter(model_name=get_settings().fallback_model_name)
        # Mọi adapter đều bọc lớp ĐO. Quota thì tiêu ở tầng điều phối
        # (`slot_extraction` cho trích slot, `DefaultSynthesisService` cho một
        # lượt thử synthesis), nên bọc ở đây không làm lệch phép đếm slot.
        llm = MeteredLLM(raw_llm)
        optional_writer = MeteredWriter(raw_llm)
        fallback_llm = MeteredLLM(raw_fallback_llm)
        embedding = OpenAIEmbeddingAdapter()
        # `ConversationTransaction` hẹp hơn `ports.AgentTransaction` (chỉ hai
        # repository Khối 2 cần). Use case chỉ chạm `sessions`/`pending_mentions`
        # nên thu hẹp là an toàn; `cast` ở đây thay cho việc nới `UnitOfWorkPort`
        # — nới port là PR contract, không phải việc của A4-4.
        typed_unit_of_work = cast("UnitOfWorkPort", unit_of_work)
        # `operations_unit_of_work` bọc đủ `SqlAlchemyAgentTransaction` (Khối 4),
        # rộng hơn `ConversationTransaction` ở trên vì A7-1 cần chạm `review_queue`.
        # Task 9 sẽ dùng lại đúng biến này khi dựng năm `*Operations`.
        operations_unit_of_work = cast(
            "UnitOfWorkPort",
            AgentUnitOfWork(session_factory, lambda session: build_agent_transaction(session, clock=clock)),
        )
        broker = InMemoryTurnEventBroker()
        self._broker = broker
        # Audit chạy nền: một lần ghi chậm không được cộng vào thời gian khách
        # chờ, vì rút ngắn đúng thời gian đó là mục tiêu của A7-4.
        self._audit_sink = BackgroundQuoteAuditSink(
            SqlAlchemyQuoteAuditUnitOfWork(session_factory=session_factory, clock=clock)
        )
        # Bốn lớp nhận diện ý định. Danh mục thực thể dựng MỘT LẦN ở đây rồi
        # dùng lại cho mọi lượt: nó chỉ đổi khi catalog đổi, và dựng lại ở mỗi
        # tin nhắn sẽ cộng vài nghìn phép chuẩn hoá chuỗi vào đúng đường chạy mà
        # p95 ≤ 6s đang đo (PRD 8.5).
        #
        # [GIẢ ĐỊNH] Danh mục dùng seed tĩnh trong `domain/entity_catalog.py`,
        # chưa đọc `vehicles` từ DB. Đây là phương án ít rủi ro nhất để bắt đầu:
        # `default_catalog(vehicle_names=...)` đã nhận sẵn tham số, nên nối DB về
        # sau là một dòng ở đây chứ không phải một thiết kế khác.
        nlu_catalog = default_catalog()
        nlu_config = NluPipelineConfig.from_env()
        nlu_pipeline = NluPipelineServiceImpl(
            rewrite_service=RewriteServiceImpl(
                rewriter=LlmTextRewriter(llm),
                known_tokens=build_known_tokens(nlu_catalog),
                max_change_ratio=nlu_config.max_change_ratio,
                min_confidence=nlu_config.min_rewrite_confidence,
                enabled=nlu_config.rewrite_enabled,
            ),
            catalog=nlu_catalog,
            config=nlu_config,
        )
        recommendation = DefaultRecommendationService(
            source=SqlAlchemyRecommendationDataSource(session_factory),
            feature_introduction_source=SqlAlchemyFeatureIntroductionSource(session_factory),
            unit_of_work=typed_unit_of_work,
        )
        offer_policy = OfferPolicyDataSource(session_factory)
        offer_adjustment_log = OfferAdjustmentLogDataSource(session_factory)
        offer_suggestion = OfferSuggestionDataSource(session_factory)
        self._operations = AgentOperations(
            review=ReviewOperations(
                operations_unit_of_work,
                image_store=ComparisonImageStore(default_comparison_image_dir()),
                image_source=build_minio_vehicle_image_source(session_factory),
                recommendation=recommendation,
                broker=broker,
                offer_policy=offer_policy,
                offer_adjustment_log=offer_adjustment_log,
                offer_suggestion=offer_suggestion,
                profile_snapshot_service=ProfileSnapshotService(),
            ),
            bottleneck_signals=BottleneckSignalOperations(
                operations_unit_of_work,
                detail_source=offer_suggestion,
                adjustment_service=OfferAdjustmentService(
                    policy=offer_policy,
                    audit_log=offer_adjustment_log,
                ),
                session_context=offer_suggestion,
            ),
            booking=BookingOperations(operations_unit_of_work),
            history=HistoryOperations(operations_unit_of_work),
            notices=NoticeOperations(operations_unit_of_work),
            analytics=AnalyticsOperations(operations_unit_of_work, clock),
            turn_traces=TurnTraceOperations(typed_unit_of_work, clock),
            conversations=ConversationLifecycleService(typed_unit_of_work),
            assignments=AssignmentOperations(operations_unit_of_work),
            sales_opportunity=SalesOpportunityService(
                repository=SalesOpportunityDataSource(session_factory, clock),
            ),
        )
        conversation_service = ConversationServiceImpl(typed_unit_of_work)
        setattr(conversation_service, "post_pitch_branch_classifier", OpenAIPostPitchBranchClassifier())
        self._services = AgentServices(
            conversation=conversation_service,
            bottleneck_detector=BudgetedBottleneckDetector(OpenAIBottleneckDetector()),
            ask_tracking=AskTrackingServiceImpl(typed_unit_of_work),
            memory=ConversationMemoryService(
                typed_unit_of_work,
                OpenAIConversationSummarizer(),
                # Không cắm thì vòng chờ giành lượt quay ba vòng trong vài mili
                # giây rồi trả 409 ngay — khách gõ tiếp lúc bot đang nghĩ ăn lỗi
                # thay vì chờ. Luật đã chốt: chờ tới 5 giây rồi mới báo bận.
                sleep=asyncio.sleep,
                jitter=lambda: random.uniform(0.0, 0.25),
            ),
            slot_extraction=SlotExtractionServiceImpl(
                llm=llm,
                unit_of_work=typed_unit_of_work,
                feature_vocabulary=vocabulary,
            ),
            slot_planning=SlotPlanningServiceImpl(),
            intent_routing=IntentRoutingServiceImpl(catalog),
            catalog_browse=CatalogBrowseServiceImpl(catalog),
            # Cùng adapter, nhưng đi qua một cửa có TÊN: `chain` cần tra
            # `vehicle_id` từ tên xe ở các lượt ngoài pipeline đề xuất.
            vehicle_names=catalog,
            compare_vehicles=CompareVehiclesServiceImpl(
                catalog=catalog,
                # Dùng lại đúng bộ resolve tên xe của nhánh tra cứu: hai nhánh
                # phải hiểu "vf5" là cùng một xe, và hai bộ resolve song song là
                # cách chắc chắn nhất để chúng lệch nhau.
                identity=IntentRoutingServiceImpl(catalog),
                media=catalog,
                # `llm`, không phải `fallback_llm`: đoạn tóm tắt chỉ diễn đạt lại
                # một bảng đã chốt, hỏng thì `_fallback_summary` đã có câu
                # deterministic thay thế — không cần tầng dự phòng thứ hai.
                summary_writer=optional_writer,
            ),
            nearby_location=NearbyLocationServiceImpl(
                locations=LocationsNearbySource(session_factory),
                geocoder=LocationsGeocoder(CachedGeocoder(session_factory=session_factory)),
                lead_writer=optional_writer,
            ),
            test_drive=TestDriveServiceImpl(
                locations=LocationsNearbySource(session_factory),
                bookings=BookingUnitOfWorkSlotCounter(operations_unit_of_work),
            ),
            feature_fit=SqlAlchemyFeatureFitSource(session_factory),
            vehicle_overview=DefaultVehicleOverviewService(
                source=SqlAlchemyVehicleOverviewSource(
                    session_factory=session_factory,
                    embedding=embedding,
                )
            ),
            vehicle_media=catalog,
            retrieval=RetrievalServiceImpl(session_factory=session_factory, embedding=embedding),
            snapshotting=DefaultSnapshottingService(
                source=SqlAlchemyCatalogSnapshotSource(session_factory),
                unit_of_work=typed_unit_of_work,
                clock=clock,
            ),
            candidate_tuning=CandidateTuningServiceImpl(differentiator=CatalogDifferentiator(catalog=catalog)),
            recommendation=recommendation,
            synthesis=DefaultSynthesisService(
                llm=llm,
                fallback_llm=fallback_llm,
                source=SqlAlchemySynthesisDataSource(session_factory),
            ),
            tco_estimation=DefaultTcoEstimationService(
                data_source=ProductTcoDataSource(session_factory),
                clock=clock,
                unit_of_work=typed_unit_of_work,
            ),
            verification=DefaultVerificationService(source=SqlAlchemyVerificationDataSource(session_factory)),
            policy_search=(
                SqlAlchemyPolicySearchAdapter(session_factory, embedding)
                if get_settings().policy_rag_enabled
                else None
            ),
            moderation=OpenAIModerationAdapter(),
            injection_judge=OpenAIInjectionJudge(),
            vague_answer_judge=OpenAIVagueAnswerJudge(),
            scope_classifier=DefaultScopeClassifierService(
                classifier=LlmScopeClassifier(llm),
                session_context=ContextVarScopeSessionContext(),
                scope_log=SqlAlchemyScopeLogUnitOfWork(session_factory=session_factory, clock=clock),
            ),
            pending_slot=PendingSlotServiceImpl(
                clarify_questions={
                    "province": MISSING_PROVINCE_QUESTION,
                    COMPARE_TARGETS_SLOT: compare_targets_retry_question(nlu_pipeline.suggested_models()),
                    LOCATION_KIND_SLOT: ASK_LOCATION_KIND_RETRY,
                    USER_LOCATION_SLOT: ASK_LOCATION_RETRY,
                },
                exhausted_replies={
                    COMPARE_TARGETS_SLOT: COMPARE_TARGETS_GIVE_UP,
                    USER_LOCATION_SLOT: LOCATION_GIVE_UP,
                    LOCATION_KIND_SLOT: LOCATION_KIND_GIVE_UP,
                },
                extractors={
                    **DEFAULT_EXTRACTORS,
                    USER_LOCATION_SLOT: message_only_extractor(location_text_from),
                    LOCATION_KIND_SLOT: message_only_extractor(location_kind_from),
                },
                fallback_extractors={
                    **FUZZY_FALLBACK_EXTRACTORS,
                    COMPARE_TARGETS_SLOT: compare_targets_extractor(nlu_catalog),
                    # [TEST_DRIVE] Lượt sau khách gõ "VF 5" trơ trọi để trả lời
                    # câu "muốn lái thử mẫu nào". Không cắm ở đây thì bản ghi chờ
                    # dựng ở `route_intent` không bao giờ giải được, và câu hỏi
                    # chỉ là chữ.
                    TEST_DRIVE_VEHICLE_SLOT: test_drive_vehicle_extractor(nlu_catalog),
                    # [ON_ROAD_PRICE] Lượt sau khách gõ "VF 5" để trả lời câu
                    # "muốn tính giá lăn bánh mẫu nào". Cùng bộ trích với lái
                    # thử — cả hai đều hỏi ĐÚNG MỘT tên xe, nên dựng bộ thứ hai
                    # là dựng một bản sẽ lệch.
                    ON_ROAD_VEHICLE_SLOT: test_drive_vehicle_extractor(nlu_catalog),
                },
            ),
            nlu_pipeline=nlu_pipeline,
            pending_intent_confirmation=PendingIntentConfirmationServiceImpl(
                suggestions=nlu_pipeline.suggested_models()
            ),
            on_road_price=OnRoadPriceServiceImpl(source=ProductTcoDataSource(session_factory)),
            task_context=ActiveTaskService(),
            quote_gate=QuoteGateServiceImpl(
                audit=self._audit_sink,
                config=QuoteGateConfig.from_env(),
                risk_flag_judge=OpenAIRiskFlagJudge(),
            ),
            turn_handoff=TurnHandoffService(operations_unit_of_work),
            profile_snapshot_service=ProfileSnapshotService(),
            offer_suggestion_service=OfferSuggestionDataSource(session_factory),
            # Sếp 2026-08-31: tool `tinh_chi_phi` chạy gpt-4o, KHÔNG dùng 5.6
            # (4o gọi tool ổn định, không cần trò reasoning_effort="none").
            tco_arg_resolver=OpenAITcoArgResolver(model_name="gpt-4o"),
            location_arg_resolver=OpenAILocationArgResolver(model_name="gpt-4o"),
            spec_arg_resolver=OpenAISpecArgResolver(model_name="gpt-4o"),
            understanding=OpenAIUnderstander(),
            # Cờ động đường agent — chỉ ĐỌC bảng `agent_feature_flags`, TTL 60s.
            agent_flag=SqlAlchemyAgentFlagAdapter(session_factory),
            # Vòng ReAct chỉ chạy khi cờ `agent_fallback` bật (mặc định TẮT).
            agent_loop=OpenAIAgentLoop(),
        )
        self._graph = None  # lõi v1 (LangGraph) đã xoá — xem chain.py

    async def shutdown(self) -> None:
        """Chờ audit nền ghi xong rồi đóng engine; gọi được nhiều lần."""

        if self._audit_sink is not None:
            # Đóng engine trước khi task nền chạy xong thì dòng audit cuối cùng
            # mất, và đó thường là dòng của lượt vừa gây sự cố.
            await self._audit_sink.drain()
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None


__all__ = [
    "AgentComposition",
    "AgentOperations",
    "ConversationTransaction",
    "SystemClock",
    "agent_database_url",
    "build_agent",
    "create_agent_services",
]
