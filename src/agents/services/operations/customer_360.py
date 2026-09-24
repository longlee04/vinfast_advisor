"""Customer 360 — gắn phiên vào cơ hội, trích thông tin khách, tính giai đoạn/độ nóng.

Chạy NỀN, không bao giờ trong luồng trả lời khách (plan Customer 360 §2.2, ràng buộc §6):
- `Customer360TurnHook`: sau `commit_core_turn`, mỗi 4 lượt, nếu cờ `customer360_attach`
  bật cho khách → đẩy `refresh_session` vào task nền.
- `sweep`: script cron (`scripts/customer360_sweep.py`) — phiên idle > 30 phút, cơ hội ngủ
  > 30 ngày → DORMANT, tính lại độ nóng theo thời gian.

Service chỉ biết domain + port; SQL ở `adapters/customer_opportunity_repository.py`,
LLM ở `adapters/customer_360_llm.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from src.agents.domain.advisory_restart import AdvisoryFlowAction, classify_advisory_flow
from src.agents.domain.agent_flag import AgentFlagState, is_enabled_for
from src.agents.domain.buyer_for import BuyerFor, detect_buyer_for
from src.agents.domain.customer360_flags import FLAG_ATTACH, FLAG_EXTRACTOR
from src.agents.domain.customer_insight import (
    MAX_EXTRACTIONS_PER_SESSION,
    CurrentInsight,
    InsightField,
    InsightSource,
    RejectReason,
    SaveAction,
    insight_scope,
    plan_save,
    validate_candidate,
)
from src.agents.domain.customer_overview import evaded_slots, missing_slots
from src.agents.domain.heat_score import HeatResult, HeatSignals, compute_heat
from src.agents.domain.opportunity_attach import (
    AttachDecision,
    AttachKind,
    Decider,
    LlmVerdict,
    OpportunityView,
    SessionFacts,
    apply_llm_verdict,
    decide,
)
from src.agents.domain.sales_stage import SalesStage, StageSignals, derive_stage

logger = logging.getLogger(__name__)

#: Phiên im lâu hơn mức này coi như "đã kết thúc" để gắn cơ hội (G3).
IDLE_MINUTES = 30
#: Hook sau lượt chạy mỗi N lượt khách (G3).
TURN_CADENCE = 4
#: Slot tầng Khách được ghi thành insight nguồn SLOT để giữ lịch sử.
_CUSTOMER_SLOTS: tuple[InsightField, ...] = (InsightField.REGISTRATION_PROVINCE, InsightField.HOME_CHARGING)


# ---------------------------------------------------------------- DTO + port


@dataclass(frozen=True, slots=True)
class Attachment:
    opportunity_id: str | None
    kind: str
    decided_by: str
    extracted_through_turn: int
    extraction_count: int
    #: Số phiên đang gắn vào cơ hội này (kể cả phiên hiện tại).
    opportunity_session_count: int = 0


@dataclass(frozen=True, slots=True)
class SessionContext:
    session_id: str
    customer_id: str
    slots: Mapping[str, object]
    user_turns: Mapping[int, str]
    turn_count: int
    last_activity_at: datetime
    attachment: Attachment | None = None


@dataclass(frozen=True, slots=True)
class NewInsight:
    field: InsightField
    value: str
    value_code: str | None
    evidence_quote: str
    turn_index: int | None
    confidence: float
    source: InsightSource
    opportunity_id: str | None
    supersedes: str | None = None


@dataclass(frozen=True, slots=True)
class HeatInputs:
    customer_id: str
    status: str
    current_stage: SalesStage
    stage_signals: StageSignals
    vehicle_type: str | None
    slots: Mapping[str, object]
    ask_counts: Mapping[str, int]
    purchase_timeframe: str | None
    has_phone: bool
    human_requested: bool
    sessions_14d: int
    payment_asked: bool
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class ClassifierResult:
    verdict: LlmVerdict | None
    confidence: float
    chosen_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    items: Sequence[Mapping[str, object]]
    model_name: str
    prompt_version: str


class Customer360Repository(Protocol):
    async def load_session_context(self, session_id: str) -> SessionContext | None: ...
    async def list_open_opportunities(self, customer_id: str) -> list[OpportunityView]: ...
    async def apply_attachment(
        self, context: SessionContext, decision: AttachDecision, buyer_for: BuyerFor, at: datetime
    ) -> str | None: ...
    async def current_insights(self, customer_id: str) -> list[CurrentInsight]: ...
    async def save_insights(
        self,
        context: SessionContext,
        rows: Sequence[NewInsight],
        *,
        extracted_through_turn: int | None,
        model_name: str | None,
        prompt_version: str | None,
        at: datetime,
    ) -> int: ...
    async def load_heat_inputs(self, opportunity_id: str, now: datetime) -> HeatInputs | None: ...
    async def save_scores(self, opportunity_id: str, stage: SalesStage, heat: HeatResult, at: datetime) -> None: ...
    async def mark_dormant(self, before: datetime) -> int: ...
    async def sessions_to_refresh(self, idle_before: datetime, active_after: datetime, limit: int) -> list[str]: ...
    async def open_opportunity_ids(self, limit: int) -> list[str]: ...
    async def move_session(
        self, session_id: str, target_opportunity_id: str | None, actor: str, at: datetime
    ) -> tuple[str, str | None, str] | None: ...
    async def record_insight_feedback(
        self, insight_id: str, verdict: str, actor: str, note: str | None, at: datetime
    ) -> bool: ...
    async def profile_needs_identity(self, customer_id: str) -> bool: ...
    async def upsert_profile_identity(
        self, customer_id: str, display_name: str | None, phone: str | None, at: datetime
    ) -> None: ...


class OpportunityClassifier(Protocol):
    async def classify(self, session_summary: str, candidates: Sequence[Mapping[str, object]]) -> ClassifierResult: ...


class InsightExtractor(Protocol):
    async def extract(self, user_turns: Mapping[int, str]) -> ExtractionResult | None: ...


class FlagReader(Protocol):
    async def load(self, name: str) -> AgentFlagState | None: ...


class CustomerIdentitySource(Protocol):
    """Tên/SĐT của khách từ module auth — agents không import model auth (plan 4F)."""

    async def lookup(self, customer_id: str) -> tuple[str | None, str | None] | None: ...


@dataclass(frozen=True, slots=True)
class RefreshResult:
    session_id: str
    opportunity_id: str | None
    rule_code: str | None
    insights_saved: int = 0
    rejected: Mapping[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------- use case


def _summary_for_classifier(context: SessionContext) -> str:
    slots = ", ".join(f"{key}={value}" for key, value in sorted(context.slots.items()) if key != "purpose_bucket")
    last_turns = [context.user_turns[index] for index in sorted(context.user_turns)[-6:]]
    return "Slot phiên: " + slots + "\nCâu khách gần nhất:\n- " + "\n- ".join(last_turns)


class Customer360Operations:
    def __init__(
        self,
        repository: Customer360Repository,
        *,
        clock: Callable[[], datetime],
        flags: FlagReader | None = None,
        classifier: OpportunityClassifier | None = None,
        extractor: InsightExtractor | None = None,
        identity: CustomerIdentitySource | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._flags = flags
        self._classifier = classifier
        self._extractor = extractor
        self._identity = identity

    async def _flag_on(self, name: str, customer_id: str) -> bool:
        if self._flags is None:
            return False
        return is_enabled_for(await self._flags.load(name), customer_id)

    async def refresh_session(self, session_id: str, *, force_extract: bool | None = None) -> RefreshResult | None:
        """Gắn phiên → cơ hội, ghi slot tầng Khách, trích insight (nếu bật), tính lại điểm."""

        context = await self._repository.load_session_context(session_id)
        if context is None:
            return None
        now = self._clock()
        attachment = context.attachment
        buyer_for = detect_buyer_for(context.user_turns[index] for index in sorted(context.user_turns))
        if attachment is not None and attachment.decided_by == Decider.ADVISOR.value:
            # TVV đã quyết thì máy không được lật lại.
            opportunity_id, rule_code = attachment.opportunity_id, None
        else:
            decision = await self._decide(context, buyer_for)
            opportunity_id = await self._repository.apply_attachment(context, decision, buyer_for, now)
            rule_code = decision.rule_code

        saved = await self._record_customer_slots(context, now)
        rejected: dict[str, int] = {}
        extract = (
            force_extract if force_extract is not None else await self._flag_on(FLAG_EXTRACTOR, context.customer_id)
        )
        if extract and self._extractor is not None:
            count, rejected = await self._extract(context, opportunity_id, now)
            saved += count
        if opportunity_id is not None:
            await self.recompute_opportunity(opportunity_id)
        await self._sync_identity(context.customer_id, now)
        return RefreshResult(session_id, opportunity_id, rule_code, saved, rejected)

    async def _decide(self, context: SessionContext, buyer_for: BuyerFor) -> AttachDecision:
        # Câu MỞ phiên ("tư vấn xe") luôn có dạng lời nhờ tư vấn — nó mở phiên, không phải
        # "tư vấn lại từ đầu" một cơ hội cũ. Chỉ các lượt sau mới tính là tín hiệu restart (R4).
        later_turns = [context.user_turns[index] for index in sorted(context.user_turns)[1:]]
        restart = any(
            classify_advisory_flow(text).action is AdvisoryFlowAction.RESTART_ADVISORY for text in later_turns
        )
        facts = SessionFacts(session_id=context.session_id, buyer_for=buyer_for, slots=context.slots, restart=restart)
        opportunities = await self._repository.list_open_opportunities(context.customer_id)
        attachment = context.attachment
        own = attachment.opportunity_id if attachment is not None else None
        # Phiên là nguồn DUY NHẤT của cơ hội nó đã sinh ra: so với chính cơ hội đó sẽ tự
        # mâu thuẫn khi khách đổi ý giữa phiên → cập nhật thẳng cơ hội của mình.
        if own is not None and attachment is not None and attachment.opportunity_session_count <= 1:
            others = [item for item in opportunities if item.opportunity_id != own]
            decision = decide(facts, others)
            if decision.kind in {AttachKind.NEW, AttachKind.AMBIGUOUS, AttachKind.SUPPORT}:
                mine = next((item for item in opportunities if item.opportunity_id == own), None)
                if mine is not None and decision.kind is not AttachKind.SUPPORT:
                    return decide(facts, [mine])
                if decision.kind is not AttachKind.AMBIGUOUS:
                    return decision
        else:
            decision = decide(facts, opportunities)
        if decision.kind is not AttachKind.AMBIGUOUS:
            return decision
        if self._classifier is None:
            return apply_llm_verdict(decision, None, 0.0, opportunities, facts)
        candidates = [
            {
                "opportunity_id": item.opportunity_id,
                "vehicle_type": item.vehicle_type,
                "buyer_for": item.buyer_for.value,
                "status": item.status,
                "slots": {key: value for key, value in item.slots.items() if key != "purpose_bucket"},
                "last_seen_at": item.last_seen_at.isoformat(),
            }
            for item in opportunities
            if item.opportunity_id in decision.candidates
        ]
        try:
            result = await self._classifier.classify(_summary_for_classifier(context), candidates)
        except Exception:  # noqa: BLE001 — phân loại hỏng thì gắn tạm chờ TVV, không làm hỏng job
            logger.warning("customer360: phan loai co hoi that bai phien %s", context.session_id, exc_info=True)
            result = ClassifierResult(None, 0.0)
        return apply_llm_verdict(decision, result.verdict, result.confidence, opportunities, facts, result.chosen_id)

    async def _record_customer_slots(self, context: SessionContext, now: datetime) -> int:
        current = await self._repository.current_insights(context.customer_id)
        rows = []
        for slot in _CUSTOMER_SLOTS:
            raw = context.slots.get(slot.value)
            if raw in (None, "", "__declined__"):
                continue
            value = str(raw).lower() if isinstance(raw, bool) else str(raw)
            plan = plan_save(slot, value, value, None, current)
            if plan.action is SaveAction.SKIP_DUPLICATE:
                continue
            rows.append(
                NewInsight(
                    field=slot,
                    value=value,
                    value_code=value,
                    evidence_quote="",
                    turn_index=None,
                    confidence=1.0,
                    source=InsightSource.SLOT,
                    opportunity_id=None,
                    supersedes=plan.superseded_id,
                )
            )
        if not rows:
            return 0
        return await self._repository.save_insights(
            context, rows, extracted_through_turn=None, model_name=None, prompt_version=None, at=now
        )

    async def _extract(
        self, context: SessionContext, opportunity_id: str | None, now: datetime
    ) -> tuple[int, dict[str, int]]:
        attachment = context.attachment
        cursor = attachment.extracted_through_turn if attachment is not None else 0
        if attachment is not None and attachment.extraction_count >= MAX_EXTRACTIONS_PER_SESSION:
            return 0, {}
        pending = {index: text for index, text in context.user_turns.items() if index > cursor}
        if not pending:
            return 0, {}
        window = dict(sorted(pending.items())[-12:])
        result = await self._extractor.extract(window) if self._extractor is not None else None
        if result is None:
            return 0, {}
        current = await self._repository.current_insights(context.customer_id)
        rejected: dict[str, int] = {}
        rows: list[NewInsight] = []
        for raw in result.items:
            candidate = validate_candidate(raw, window)
            if isinstance(candidate, RejectReason):
                rejected[candidate.value] = rejected.get(candidate.value, 0) + 1
                continue
            scope = insight_scope(candidate.field, opportunity_id)
            plan = plan_save(
                candidate.field, candidate.value, candidate.value_code, scope, [*current, *_as_current(rows)]
            )
            if plan.action is SaveAction.SKIP_DUPLICATE:
                continue
            rows.append(
                NewInsight(
                    field=candidate.field,
                    value=candidate.value,
                    value_code=candidate.value_code,
                    evidence_quote=candidate.evidence_quote,
                    turn_index=candidate.turn_index,
                    confidence=candidate.confidence,
                    source=InsightSource.LLM,
                    opportunity_id=scope,
                    supersedes=plan.superseded_id,
                )
            )
        if rejected:
            logger.info("customer360.extract rejected=%s phien=%s", rejected, context.session_id)
        saved = await self._repository.save_insights(
            context,
            rows,
            extracted_through_turn=max(window),
            model_name=result.model_name,
            prompt_version=result.prompt_version,
            at=now,
        )
        return saved, rejected

    async def recompute_opportunity(self, opportunity_id: str) -> HeatResult | None:
        now = self._clock()
        inputs = await self._repository.load_heat_inputs(opportunity_id, now)
        if inputs is None:
            return None
        stage = derive_stage(inputs.stage_signals, inputs.current_stage)
        missing = missing_slots(inputs.vehicle_type, inputs.slots)
        heat = compute_heat(
            HeatSignals(
                stage=stage,
                purchase_timeframe=inputs.purchase_timeframe,
                has_phone=inputs.has_phone,
                human_requested=inputs.human_requested,
                sessions_14d=inputs.sessions_14d,
                budget_stated=any(inputs.slots.get(slot) for slot in ("budget_stated_vnd", "budget_max_vnd")),
                payment_asked=inputs.payment_asked,
                evaded_slots=len(evaded_slots(missing, inputs.ask_counts)),
                days_since_seen=max(0.0, (now - inputs.last_seen_at).total_seconds() / 86_400),
            )
        )
        await self._repository.save_scores(opportunity_id, stage, heat, now)
        return heat

    async def _sync_identity(self, customer_id: str, now: datetime) -> None:
        if self._identity is None or not await self._repository.profile_needs_identity(customer_id):
            return
        try:
            found = await self._identity.lookup(customer_id)
        except Exception:  # noqa: BLE001 — thiếu tên không được làm hỏng job
            logger.warning("customer360: khong tra duoc danh tinh khach", exc_info=True)
            return
        if found is not None and any(found):
            await self._repository.upsert_profile_identity(customer_id, found[0], found[1], now)

    async def sweep(self, *, limit: int = 200) -> dict[str, int]:
        """Việc định kỳ: DORMANT, gắn phiên idle, tính lại độ nóng (điểm giảm theo thời gian)."""

        now = self._clock()
        dormant = await self._repository.mark_dormant(now - timedelta(days=30))
        refreshed = 0
        for session_id in await self._repository.sessions_to_refresh(
            now - timedelta(minutes=IDLE_MINUTES), now - timedelta(days=2), limit
        ):
            context = await self._repository.load_session_context(session_id)
            if context is None or not await self._flag_on(FLAG_ATTACH, context.customer_id):
                continue
            await self.refresh_session(session_id)
            refreshed += 1
        rescored = 0
        for opportunity_id in await self._repository.open_opportunity_ids(limit):
            await self.recompute_opportunity(opportunity_id)
            rescored += 1
        return {"dormant": dormant, "refreshed": refreshed, "rescored": rescored}

    async def move_session(self, session_id: str, target_opportunity_id: str | None, actor: str) -> str | None:
        """TVV Tách (`target=None` → cơ hội mới) / Gộp vào cơ hội khác. Ghi `decided_by=ADVISOR`."""

        moved = await self._repository.move_session(session_id, target_opportunity_id, actor, self._clock())
        if moved is None:
            return None
        _customer_id, previous, current = moved
        for opportunity_id in {previous, current} - {None}:
            await self.recompute_opportunity(str(opportunity_id))
        return current

    async def insight_feedback(self, insight_id: str, verdict: str, actor: str, note: str | None) -> bool:
        return await self._repository.record_insight_feedback(insight_id, verdict, actor, note, self._clock())


def _as_current(rows: Sequence[NewInsight]) -> list[CurrentInsight]:
    return [
        CurrentInsight(f"pending-{index}", row.field, row.opportunity_id, row.value, row.value_code)
        for index, row in enumerate(rows)
    ]


# ---------------------------------------------------------------- hook sau lượt


class BackgroundScheduler(Protocol):
    def schedule(self, work: Callable[[], Awaitable[object]], *, label: str) -> None: ...


class Customer360TurnHook:
    """Gọi SAU khi lượt đã commit. Cờ tắt → không làm gì (hành vi agent y nguyên)."""

    def __init__(
        self,
        operations: Customer360Operations,
        flags: FlagReader,
        scheduler: BackgroundScheduler,
        *,
        every: int = TURN_CADENCE,
    ) -> None:
        self._operations = operations
        self._flags = flags
        self._scheduler = scheduler
        self._every = every

    async def __call__(self, *, session_id: str, customer_id: str, turn_count: int) -> None:
        if turn_count <= 0 or turn_count % self._every != 0:
            return
        if not is_enabled_for(await self._flags.load(FLAG_ATTACH), customer_id):
            return
        self._scheduler.schedule(
            lambda: self._operations.refresh_session(session_id), label=f"customer360:{session_id}"
        )


__all__ = [
    "Attachment",
    "ClassifierResult",
    "Customer360Operations",
    "Customer360Repository",
    "Customer360TurnHook",
    "ExtractionResult",
    "HeatInputs",
    "NewInsight",
    "RefreshResult",
    "SessionContext",
]
