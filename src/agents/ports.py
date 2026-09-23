"""Cổng (Protocol) mà `adapters/` implement — chữ ký, không phải thân (mục 6.0/6.4).

Đóng băng ở Ngày 0 (§2.1 docs/team_split.md): đổi chữ ký là một PR riêng, cả 4
người duyệt, nêu rõ ai đang phụ thuộc chữ ký cũ. `adapters/` là nơi DUY NHẤT
biết SQLAlchemy/LLM SDK cụ thể (mục 6.5b) — vì vậy các Protocol ở đây không
import `sqlalchemy`; `UnitOfWorkPort.transaction()` trả về một `AgentTransaction`
gồm các repository Protocol, không trả `AsyncSession` thô (cùng quy ước
`DocumentUnitOfWork`/`AuthUnitOfWork` đã có).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol
from uuid import UUID

from src.agents.contracts import (
    CandidateInput,
    EvidenceInput,
    FeatureAssertion,
    FilterCriteria,
    LLMExtractionPayload,
    QuoteAuditRecord,
    ScoreInput,
    VehicleFacts,
    VehicleMatch,
)
from src.agents.core.understand import UnderstandOutcome
from src.agents.domain.agent_flag import AgentFlagState
from src.agents.domain.agent_tools import AgentToolCall, AgentToolResult
from src.agents.domain.bottleneck_signal import (
    BottleneckSignal,
    ConfirmedBottleneckEvidence,
    OpportunitySignal,
    SignalInsert,
    SignalVerdict,
)
from src.agents.domain.catalog_browse import BrowseEntry
from src.agents.domain.conversation_memory import (
    Conversation,
    ConversationCursor,
    ConversationMessage,
    ConversationPage,
    ConversationSummary,
    CoreTurnLease,
    LeaseBusy,
    MessageCursor,
    MessagePage,
    TerminalReplay,
    TurnClaim,
    TurnOutcome,
    TurnOutcomeStatus,
    WorkingMemoryProjection,
)
from src.agents.domain.session_offer import SessionOffer
from src.agents.domain.turn_trace import TurnTrace
from src.agents.domain.values import SlotName, SlotValue, VehicleType
from src.agents.tools.tco import DetailedTcoResult
from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentSourceKind,
)

if TYPE_CHECKING:
    from src.agents.services.operations.review import QueueEntry, ReviewItem


class VehicleImageSource(Protocol):
    """Anh nhan dien cua xe, da chuan hoa san o buoc dong bo."""

    async def load(self, vehicle_id: UUID) -> bytes | None: ...


class LLMPort(Protocol):
    """Cổng duy nhất gọi LLM thật — hai điểm chạm: A2-3 trích slot, A5-6 synthesis.

    Vai LLM bị bó chặt (mục 6.8): không viết SQL, không tự quyết hỏi gì tiếp,
    không viết chữ số trong `synthesize`.
    """

    async def extract_slots(
        self,
        *,
        vehicle_type: VehicleType | None,
        feature_vocabulary: Sequence[str],
        conversation_history: str | WorkingMemoryProjection,
        user_message: str,
    ) -> LLMExtractionPayload: ...

    async def synthesize(self, *, prompt: str) -> str: ...


class PolicySearchPort(Protocol):
    """Hybrid search port for policy documents."""

    async def search(
        self,
        *,
        query: str,
        top_k: int = 5,
        category_filter: str | None = None,
        effective_after: str | None = None,
        vehicle_id: str | None = None,
    ) -> list[dict]: ...


class EmbeddingPort(Protocol):
    """Implement qua `langchain-openai` (mục 4) — không model local ở MVP."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FeatureVocabularyPort(Protocol):
    """A2-4: enum `feature_code` dựng tại runtime từ `feature_definitions`.

    Danh sách feature KHÔNG được viết cứng trong prompt (mục 6.7b): thêm feature
    là `INSERT` + restart, không sửa prompt, không chạy lại test slot cũ.
    """

    async def list_active_features(self, vehicle_type: VehicleType) -> list[tuple[str, str]]: ...


class CatalogReadPort(Protocol):
    """Lớp 1 — SQL hard filter dựng sẵn trong code (mục 7.1 schema, A1-2)."""

    async def hard_filter(self, criteria: FilterCriteria) -> list[UUID]: ...

    # [A4-7] Liệt kê toàn bộ xe ĐANG BÁN của một loại, KHÔNG lọc theo nhu cầu.
    # Tách khỏi `hard_filter` dù cùng đọc `vehicles`: `hard_filter` phục vụ Lớp 1
    # nên luôn `JOIN` giá và cắt mất xe chưa công bố giá — đúng cho việc chọn xe,
    # sai cho việc liệt kê danh mục, vì xe chưa có giá vẫn đang được bán.
    async def browse_catalog(self, vehicle_type: VehicleType) -> list[BrowseEntry]: ...

    async def differentiators(self, vehicle_ids: list[UUID]) -> list[str]: ...

    async def resolve_vehicle_names(self, mentions: Sequence[str]) -> list[VehicleMatch]: ...

    async def vehicle_facts(self, vehicle_ids: Sequence[UUID]) -> list[VehicleFacts]: ...


class NearbyPlace(NamedTuple):
    """Một hàng của bảng `locations` mà cổng địa điểm trả về."""

    id: str
    location_type: str
    category_label: str
    name: str
    address: str
    latitude: float
    longitude: float
    distance_km: float | None
    hotline: str | None
    open_time: str | None
    close_time: str | None
    status: str | None


class NearbyLocationPort(Protocol):
    """[FIND_NEARBY_LOCATION] Đọc địa điểm gần một toạ độ, đã sắp theo khoảng cách."""

    async def nearest(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        location_types: Sequence[str] = (),
        limit: int = 5,
    ) -> list[NearbyPlace]: ...


class GeocodedPlace(NamedTuple):
    """Toạ độ kèm tên chuẩn hoá mà nhà cung cấp trả về."""

    latitude: float
    longitude: float
    display_name: str


class GeocodePort(Protocol):
    """Địa danh khách gõ → toạ độ. `None` nghĩa là KHÔNG tìm ra, không phải lỗi."""

    async def geocode(self, location_text: str) -> GeocodedPlace | None: ...


class FeatureRetrievalPort(Protocol):
    """Lớp 2 — một cửa, năm nhánh ẩn bên trong adapter (mục 7.2 schema, A1-3/6/7)."""

    async def resolve(
        self,
        utterance: str,
        vehicle_type: VehicleType,
        candidate_ids: list[UUID],
    ) -> list[FeatureAssertion]: ...


class ClockPort(Protocol):
    """Thời điểm hệ thống — tách khỏi `datetime.now()` để test tất định (A9-2)."""

    def now(self) -> datetime: ...


class SessionRepository(Protocol):
    """`conversation_sessions` + `conversation_slots` (A2-2). Sửa slot là UPDATE, không append."""

    async def ensure_session(
        self, session_id: str, customer_id: str, vehicle_type_hint: VehicleType | None
    ) -> None: ...

    async def get_slots(self, session_id: str, customer_id: str) -> dict[SlotName, SlotValue]: ...

    async def upsert_slot(self, session_id: str, slot_name: SlotName, value: SlotValue) -> None: ...

    async def restart_advisory(self, session_id: str) -> None: ...

    # A7-5: bộ nhớ báo giá gần nhất của phiên. `save` KHÔNG bao giờ được gọi với
    # `None` để "dọn dẹp": chỉ một báo giá mới mới được ghi đè giá trị cũ, còn
    # một lượt xác nhận thì không đụng tới nó (yêu cầu mục 4 của A7-5).
    async def load_quote_decision(self, session_id: str) -> tuple[dict | None, datetime | None]: ...

    async def save_quote_decision(
        self, session_id: str, evaluation: Mapping[str, object], sent_at: datetime
    ) -> None: ...

    # A7-10: slot đang chờ khách trả lời. Bổ sung vào Protocol ở đây (bản cài
    # đặt đã có sẵn từ A7-10, chỉ khai báo bị sót nên mypy không kiểm được
    # `ConversationServiceImpl.load_pending_slot`). Thêm khai báo cho một method
    # mọi implementation đã có là thay đổi thuần cộng, không phá chữ ký nào.
    async def load_pending_slot(self, session_id: str) -> dict | None: ...

    async def save_pending_slot(self, session_id: str, payload: Mapping[str, object] | None) -> None: ...

    async def load_active_task(self, session_id: str) -> dict | None: ...

    async def save_active_task(self, session_id: str, payload: Mapping[str, object] | None) -> None: ...

    # Lớp 4 nhận diện ý định: câu xác nhận đang chờ khách gật/lắc. `None` ở
    # `save` nghĩa là XOÁ — cùng quy ước với `save_pending_slot` của A7-10, và
    # NGƯỢC với `save_quote_decision` ngay trên (nơi `None` không bao giờ được
    # ghi xuống). Hai quy ước khác nhau vì hai vòng đời khác nhau: một câu xác
    # nhận đã được trả lời thì phải biến mất, còn bộ nhớ báo giá thì không.
    async def load_pending_intent_confirmation(self, session_id: str) -> dict | None: ...

    async def save_pending_intent_confirmation(self, session_id: str, payload: Mapping[str, object] | None) -> None: ...

    async def load_user_location(self, session_id: str) -> dict | None: ...

    async def save_user_location(self, session_id: str, payload: Mapping[str, object] | None) -> None: ...

    # A (máy trạng thái sở hữu phiên): đọc/ghi `ownership` (`AI`/`PENDING_HANDOFF`/
    # `HUMAN`) — nguồn cho `ConversationServiceImpl.load_handoff_state`.
    async def get_ownership(self, session_id: str) -> str | None: ...

    async def set_ownership(self, session_id: str, ownership: str) -> bool: ...


class PendingFeatureMentionPort(Protocol):
    """Persist unresolved feature mentions until required slots are complete."""

    async def record(self, session_id: str, customer_id: str, mentions: list[str]) -> None: ...

    async def consume(self, session_id: str, customer_id: str) -> list[str]: ...


class MessageRepository(Protocol):
    """Durable conversation messages and client-turn idempotency lookup."""

    async def find_user_by_client_turn(self, session_id: UUID, client_turn_id: str) -> tuple[UUID, datetime] | None: ...

    async def find_assistant_after(self, session_id: UUID, created_after: datetime) -> tuple[UUID, str] | None: ...

    async def add(
        self,
        *,
        session_id: UUID,
        role: str,
        content: str,
        client_turn_id: str | None = None,
        durable_for_review_id: UUID | None = None,
    ) -> UUID: ...

    async def list_for_session(
        self, session_id: UUID, limit: int = 100
    ) -> list[tuple[UUID, str, str, str | None, datetime]]: ...

    async def latest_content(self, session_id: UUID) -> str | None:
        """Nội dung tin nhắn CUỐI của phiên (khách/bot/TVV), hoặc `None` khi chưa có tin."""
        ...


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Một phiên ACTIVE hoạt động gần đây — đầu vào màn Cơ hội bán hàng."""

    session_id: UUID
    customer_id: str
    last_activity_at: datetime


class ConversationMemoryRepository(Protocol):
    """Persist an owned, append-only visible transcript and its summary."""

    async def find_by_client_turn(
        self, session_id: str, customer_id: str, client_turn_id: UUID
    ) -> tuple[ConversationMessage, ...]: ...

    async def append(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        client_turn_id: UUID | None,
    ) -> ConversationMessage: ...

    async def append_delivery(self, session_id: UUID, content: str, delivery_id: UUID) -> ConversationMessage: ...

    async def load_recent(
        self, session_id: str, customer_id: str, limit: int
    ) -> tuple[ConversationSummary | None, tuple[ConversationMessage, ...]]: ...

    async def save_summary(self, session_id: str, customer_id: str, summary: ConversationSummary) -> None: ...

    # T10 (C7): các phiên ACTIVE hoạt động gần đây — nguồn cho màn Cơ hội bán hàng.
    async def list_active_sessions(self, since: datetime) -> list[SessionSummary]: ...


class ConversationRepository(Protocol):
    """Manage an authenticated customer's conversation lifecycle."""

    async def create(self, customer_id: str, *, conversation_id: UUID | None = None) -> Conversation: ...

    async def list_owned(
        self,
        customer_id: str,
        *,
        limit: int,
        cursor: ConversationCursor | None = None,
        include_archived: bool = False,
    ) -> ConversationPage: ...

    async def get_owned(self, conversation_id: UUID, customer_id: str) -> Conversation: ...

    async def archive(self, conversation_id: UUID, customer_id: str) -> Conversation: ...

    async def delete(self, conversation_id: UUID, customer_id: str) -> None: ...

    async def read_messages(
        self,
        conversation_id: UUID,
        customer_id: str,
        *,
        limit: int,
        cursor: MessageCursor | None = None,
    ) -> MessagePage: ...


class TurnOutcomeRepository(Protocol):
    """Own idempotent turn claims and exact replay payloads."""

    async def claim(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnClaim: ...

    async def acquire_core_turn_lease(
        self,
        conversation_id: UUID,
        customer_id: str,
        client_turn_id: UUID,
        *,
        lease_seconds: int,
    ) -> CoreTurnLease | TerminalReplay | LeaseBusy: ...

    async def assert_core_turn_lease(self, lease: CoreTurnLease) -> None: ...

    async def get(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnOutcome | None: ...

    async def latest(self, conversation_id: UUID, customer_id: str) -> TurnOutcome | None: ...

    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome: ...

    async def fail(
        self,
        conversation_id: UUID,
        client_turn_id: UUID,
        *,
        error_category: str,
    ) -> TurnOutcome: ...

    async def set_review_terminal(
        self,
        review_id: UUID,
        *,
        status: TurnOutcomeStatus,
        message_id: UUID | None = None,
        delivered_content: str | None = None,
    ) -> TurnOutcome | None: ...


class ConversationSummarizerPort(Protocol):
    """Update a compact summary from exactly one completed visible pair."""

    async def summarize(self, *, previous_summary: str, user_message: str, assistant_response: str) -> str: ...


class RunRepository(Protocol):
    """`agent_runs` + `run_snapshots` (A5-1/A5-2)."""

    async def create_run(self, session_id: str) -> UUID: ...

    async def set_state(self, run_id: UUID, state: str) -> None: ...

    async def save_snapshot(self, run_id: UUID, payload: dict) -> None: ...

    async def save_evidence(self, run_id: UUID, facts: Sequence[EvidenceInput]) -> None: ...

    async def save_candidates(self, run_id: UUID, candidates: Sequence[CandidateInput]) -> None: ...

    async def save_scores(self, run_id: UUID, scores: Sequence[ScoreInput]) -> None: ...

    async def set_candidate_ranks(self, run_id: UUID, ranks: Mapping[UUID, int]) -> None: ...

    async def ranked_vehicle_ids(self, run_id: UUID) -> list[UUID]: ...

    async def save_tco_estimate(self, run_id: UUID, result: DetailedTcoResult) -> None: ...


class ReviewQueueRepository(Protocol):
    """`review_queue` — claim CAS + lease (A7-1/2/3)."""

    async def enqueue(
        self,
        run_id: UUID,
        session_id: UUID,
        content: str,
        snapshot: object | None = None,
    ) -> UUID: ...

    async def claim(self, queue_id: UUID, advisor_id: str, lease_minutes: int) -> bool: ...

    async def resolve(self, queue_id: UUID, advisor_id: str, status: str, edited_content: str | None) -> None: ...

    async def customer_owns_session(self, session_id: UUID, customer_id: str) -> bool: ...

    async def list_for_session(self, session_id: UUID) -> list[ReviewItem]: ...

    async def list_pending(self) -> list[QueueEntry]: ...

    async def queue_stats(self) -> dict[str, int]: ...


class QuoteAuditPort(Protocol):
    """[A7-4] Ghi audit bất đồng bộ cho mọi quyết định của cổng rủi ro báo giá.

    Cổng riêng, không nhét vào `AgentTransaction`: audit KHÔNG được chia sẻ số
    phận với transaction nghiệp vụ. Ghi audit hỏng thì lượt của khách vẫn phải
    chạy, và ngược lại một lượt bị rollback vẫn phải để lại dấu vết đã quyết
    định gì — đúng lý do `out_of_scope_log` (A6-2) cũng có unit of work riêng.
    """

    async def record(self, entry: QuoteAuditRecord) -> None: ...


class NoticeRepository(Protocol):
    """`internal_notices` + `notice_reads` (A8-4) — trạng thái đã đọc riêng từng người."""

    async def create_notice(self, title: str, content: str, priority: str, created_by: str) -> UUID: ...

    async def mark_read(self, notice_id: UUID, advisor_id: str) -> None: ...


class BottleneckSignalRepository(Protocol):
    """Persist and verify anchored customer-turn bottleneck signals."""

    async def latest_recommendation_anchor(self, session_id: UUID, current_client_turn_id: UUID) -> UUID | None: ...

    async def confirmed_evidence(
        self, session_id: UUID, anchor_client_turn_id: UUID
    ) -> tuple[ConfirmedBottleneckEvidence, ...]: ...

    async def insert(self, signal: SignalInsert) -> BottleneckSignal: ...

    async def list_pending(self) -> tuple[BottleneckSignal, ...]: ...

    async def get(self, signal_id: UUID) -> BottleneckSignal: ...

    async def claim(self, signal_id: UUID, advisor_id: str, lease_minutes: int = 15) -> bool: ...

    async def decide(self, signal_id: UUID, advisor_id: str, verdict: SignalVerdict) -> BottleneckSignal: ...

    async def list_opportunities(self, since: datetime, limit: int) -> tuple[OpportunitySignal, ...]: ...


class SessionOfferRepository(Protocol):
    """Persist and load ACTIVE session-scoped offers (T4)."""

    async def insert(
        self,
        *,
        session_id: UUID,
        source_kind: str,
        promotion_code: str,
        value_snapshot: dict,
        approved_by: str,
        expires_at: datetime | None,
        source_signal_id: UUID | None = None,
        source_review_id: UUID | None = None,
    ) -> SessionOffer: ...

    async def active_for_session(self, session_id: str) -> list[SessionOffer]: ...


class TurnTraceRepository(Protocol):
    """Ghi vệt quyết định của một lượt — bảng QUAN SÁT, chỉ ghi."""

    async def record(self, trace: TurnTrace) -> None: ...


class CoreStateRepositoryPort(Protocol):
    """Trạng thái lõi v2 — một hàng/phiên. Chỉ `core/run_turn.py` ghi."""

    async def load(self, session_id: str) -> Any: ...

    async def save(self, state: Any) -> None: ...

    async def exists(self, session_id: str) -> bool: ...


class AgentTransaction(Protocol):
    """Bó repository trong phạm vi một transaction (mục 6.4) — cùng hình `DocumentTransaction`."""

    sessions: SessionRepository
    pending_mentions: PendingFeatureMentionPort
    memory: ConversationMemoryRepository
    conversations: ConversationRepository
    outcomes: TurnOutcomeRepository
    runs: RunRepository
    review_queue: ReviewQueueRepository
    bottleneck_signals: BottleneckSignalRepository
    session_offers: SessionOfferRepository
    notices: NoticeRepository
    turn_traces: TurnTraceRepository
    core_state: CoreStateRepositoryPort


class OfferSuggestionPort(Protocol):
    """Đề xuất ưu đãi cho một hồ sơ — agents định nghĩa port, products implement."""

    async def suggest(self, snapshot: object, at: datetime) -> object: ...


class OfferPolicyPort(Protocol):
    """Validate biên độ điều chỉnh + re-validate promotion (products implement).

    Trả ``None`` khi hợp lệ, hoặc chuỗi lý do khi vi phạm — products không cần
    import exception của agents (tránh phụ thuộc ngược).
    """

    async def validate_adjustment(self, *, adjustment: OfferAdjustment) -> str | None: ...

    async def validate_promotion_active(self, *, promotion_code: str, at: datetime) -> str | None: ...

    async def list_policies(self) -> list[dict]: ...


class OfferAdjustmentLogPort(Protocol):
    """Ghi offer_adjustment_log (bảng products) — products implement."""

    async def record(
        self,
        *,
        source_kind: OfferAdjustmentSourceKind,
        source_id: UUID,
        review_id: UUID | None,
        advisor_id: str,
        promotion_code: str,
        adjustment_type: str,
        old_value: str | None,
        new_value: str | None,
        reason: str | None,
    ) -> None: ...


class UnitOfWorkPort(Protocol):
    """Ranh giới transaction tường minh — use case (`services/`) mở/đóng, repository không tự mở (mục 6.4).

    Một lượt hội thoại KHÔNG phải một transaction: transaction bọc từng bước
    ghi, không bọc cả lượt (mục 6.4) — tránh treo connection pool khi LLM
    đang chạy giữa lượt.
    """

    def transaction(self) -> AbstractAsyncContextManager[AgentTransaction]: ...


class UnderstandingPort(Protocol):
    """Một cửa LLM của lõi v2 (spec 2026-08-29 mục 5).

    Cùng hình với `core.understand.Understander` — bản ở `core/` để lõi không
    phải import `ports.py`, bản này để `AgentServices` khai kiểu như mọi cổng
    khác. `tests/agents/unit/core/test_understand_wiring.py` chốt hai bản không
    trôi khỏi nhau.

    KHÔNG raise: hỏng thì trả `UnderstandOutcome(raw=None, error=...)`.
    """

    async def understand(self, *, system_prompt: str, user_prompt: str) -> UnderstandOutcome: ...


class AgentFlagPort(Protocol):
    """Đọc một cờ động của đường agent (plan agent-migration Bước 3).

    KHÔNG raise: DB hỏng, hàng chưa có → `None`, và `None` nghĩa là TẮT
    (`domain/agent_flag.is_enabled_for`). Adapter tự cache TTL — nơi gọi cứ
    hỏi mỗi lượt.
    """

    async def load(self, name: str) -> AgentFlagState | None: ...


@dataclass(frozen=True, slots=True)
class AgentLoopOutcome:
    """Kết quả một vòng ReAct (plan agent-migration Bước 5, §2.2).

    `answer is None` nghĩa là loop KHÔNG ra được câu trả lời — nơi gọi phải
    chạy đúng đường tất định đang chạy hôm nay. `steps` là vệt quan sát:
    mỗi bước `{"tool", "args_keys", "ok", "error", "ms"}` — CHỈ tên khoá của
    args, không bao giờ giá trị (args chứa chữ khách).
    """

    answer: str | None = None
    steps: tuple[Mapping[str, Any], ...] = ()
    error: str = ""
    llm_calls: int = 0


class AgentLoopPort(Protocol):
    """KHONG raise: hong kieu gi cung tra AgentLoopOutcome(answer=None, error=...)."""

    async def run(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        execute: Callable[[AgentToolCall], Awaitable[AgentToolResult]],
        max_steps: int,
        step_timeout_seconds: float,
        total_timeout_seconds: float,
    ) -> AgentLoopOutcome: ...
