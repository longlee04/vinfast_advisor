"""Run eval fixtures through production extraction and slot-policy code."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol

from eval.conversation.models import (
    ConversationDataset,
    ConversationRun,
    ConversationScenario,
    ConversationTurn,
    Decision,
    ExtractionPayload,
    ScenarioEvaluation,
    TurnEvaluation,
)
from eval.conversation.models import SlotName as EvalSlotName
from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.conversation_memory import (
    ConversationMessage,
    ConversationSummary,
    build_working_memory,
)
from src.agents.domain.slot_policy import next_slot
from src.agents.domain.slot_salvage import is_non_answer
from src.agents.domain.values import SlotName, SlotValue, VehicleType
from src.agents.services.slot_extraction import SlotExtractionServiceImpl
from src.agents.services.slot_planning import SlotPlanningServiceImpl


class ExtractionLlm(Protocol):
    """Narrow LLM surface used by the evaluation runner."""

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload: ...

    async def synthesize(self, *, prompt: str) -> str: ...


@dataclass
class InMemorySessions:
    """Session repository retaining one current value for each slot."""

    values: dict[SlotName, SlotValue] = field(default_factory=dict)

    async def ensure_session(self, session_id: str, customer_id: str, vehicle_type_hint: VehicleType | None) -> None:
        if vehicle_type_hint is not None:
            self.values.setdefault(SlotName.VEHICLE_TYPE, vehicle_type_hint.value)

    async def get_slots(self, session_id: str, customer_id: str) -> dict[SlotName, SlotValue]:
        return dict(self.values)

    async def upsert_slot(self, session_id: str, slot_name: SlotName, value: SlotValue) -> None:
        self.values[slot_name] = value


@dataclass
class InMemoryPendingMentions:
    """Pending feature store used only to satisfy the extraction transaction."""

    values: list[str] = field(default_factory=list)

    async def record(self, session_id: str, customer_id: str, mentions: list[str]) -> None:
        self.values.extend(mentions)

    async def consume(self, session_id: str, customer_id: str) -> list[str]:
        values = list(self.values)
        self.values.clear()
        return values


@dataclass
class EvaluationTransaction:
    sessions: InMemorySessions
    pending_mentions: InMemoryPendingMentions


class EvaluationUnitOfWork:
    """Minimal deterministic transaction boundary for offline evaluation."""

    def __init__(self, sessions: InMemorySessions) -> None:
        self._transaction = EvaluationTransaction(sessions, InMemoryPendingMentions())

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[EvaluationTransaction]:
        yield self._transaction


_ARCHITECTURE_ONLY_FIELDS = frozenset(
    {"topics", "severity", "human_requested", "variant_mentions", "constraint_updates"}
)


class ScriptedLlm:
    """Return dataset payloads in order; never call a network service."""

    def __init__(self, payloads: Sequence[ExtractionPayload]) -> None:
        self._payloads = list(payloads)
        self.calls = 0

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
        if self.calls >= len(self._payloads):
            raise RuntimeError("scripted LLM đã hết payload")
        payload = self._payloads[self.calls]
        self.calls += 1
        # Field của "kiến trúc mới" (dev/ngoc) chỉ sống trong dataset eval — payload
        # production không có chúng, soi nguyên sang là ValidationError.
        data = {
            key: value
            for key, value in payload.model_dump().items()
            if key not in _ARCHITECTURE_ONLY_FIELDS and value is not None
        }
        return LLMExtractionPayload.model_validate(data)

    async def synthesize(self, *, prompt: str) -> str:
        return prompt


class CapturingLlm:
    """Retain the raw payload so reports separate LLM output from normalization."""

    def __init__(self, delegate: ExtractionLlm) -> None:
        self._delegate = delegate
        self.last_payload = LLMExtractionPayload()

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
        raw = await self._delegate.extract_slots(**kwargs)
        self.last_payload = LLMExtractionPayload.model_validate(raw)
        return self.last_payload

    async def synthesize(self, *, prompt: str) -> str:
        return await self._delegate.synthesize(prompt=prompt)


def _vehicle_type(slots: dict[SlotName, SlotValue]) -> VehicleType | None:
    raw = slots.get(SlotName.VEHICLE_TYPE)
    if not isinstance(raw, str):
        return None
    try:
        return VehicleType(raw)
    except ValueError:
        return None


def _runtime_slots(
    slots: dict[EvalSlotName, SlotValue],
) -> dict[SlotName, SlotValue]:
    return {SlotName(slot.value): value for slot, value in slots.items()}


def _eval_slots(slots: dict[SlotName, SlotValue]) -> dict[EvalSlotName, SlotValue]:
    return {EvalSlotName(slot.value): value for slot, value in slots.items()}


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _decision(intents: list[str], next_slot_name: EvalSlotName | None, task: str | None = None) -> Decision:
    values = set(intents)
    # [COMPARE_VEHICLES] Xét trước `HYBRID`: bộ hoà giải đã gỡ mọi nhãn khác khi
    # gắn nhãn so sánh, nên hai điều kiện không bao giờ cùng đúng — thứ tự này
    # chỉ để đọc code khớp với thứ tự ưu tiên ở `nodes/route_intent`.
    if "COMPARE_VEHICLES" in values:
        return Decision.COMPARE
    # `task` (IntentType) là trục riêng của develop: xin gặp người / khiếu nại và
    # hỏi chính sách không đi qua cây slot, nên quyết định đọc từ đó (golden Ngọc).
    if task in {"HUMAN_REQUEST", "COMPLAINT"}:
        return Decision.HANDOFF
    if task == "POLICY_QUERY" and not values:
        return Decision.POLICY
    if {"ADVISORY", "CATALOG_LOOKUP"} <= values:
        return Decision.HYBRID
    if "CATALOG_BROWSE" in values:
        return Decision.BROWSE
    if "CATALOG_LOOKUP" in values:
        return Decision.LOOKUP
    if "ADVISORY" in values:
        return Decision.ASK if next_slot_name is not None else Decision.RETRIEVE
    return Decision.CLARIFY_INTENT


async def _run_scenario(
    scenario: ConversationScenario,
    *,
    llm: ExtractionLlm,
) -> ScenarioEvaluation:
    sessions = InMemorySessions(_runtime_slots(scenario.initial_slots))
    capturing_llm = CapturingLlm(llm)
    service = SlotExtractionServiceImpl(  # type: ignore[arg-type]
        capturing_llm, EvaluationUnitOfWork(sessions)
    )
    planner = SlotPlanningServiceImpl()
    ask_counts: dict[str, int] = {}
    turn_results: list[TurnEvaluation] = []
    completed_at_turn: int | None = None

    for turn_number, turn in enumerate(scenario.turns, start=1):
        current_type = _vehicle_type(sessions.values)
        extracted = await service.extract(
            session_id=scenario.id,
            customer_id="offline-eval",
            vehicle_type=current_type.value if current_type is not None else None,
            user_message=turn.user_message,
            conversation_history=_memory_context(turn, actual_slots=_eval_slots(sessions.values)),
        )
        actual_runtime_slots = dict(sessions.values)
        resolved_type = _vehicle_type(actual_runtime_slots)
        # Suy loại xe (T3) — giống `ask_or_retrieve._decide_ask_or_retrieve`.
        passenger_count = actual_runtime_slots.get(SlotName.PASSENGER_COUNT)
        budget = actual_runtime_slots.get(SlotName.BUDGET_MAX_VND)
        conflict = (
            isinstance(passenger_count, int)
            and passenger_count >= 3
            and isinstance(budget, (int, float))
            and budget < 188_000_000
        )
        if conflict and resolved_type is not None:
            del sessions.values[SlotName.VEHICLE_TYPE]
            actual_runtime_slots = dict(sessions.values)
            resolved_type = None
        elif resolved_type is None:
            inferred_type, inferred = planner.inferred_vehicle_type(actual_runtime_slots)
            if inferred and inferred_type is not None:
                sessions.values[SlotName.VEHICLE_TYPE] = inferred_type.value
                actual_runtime_slots = dict(sessions.values)
                resolved_type = inferred_type
        actual_slots = _eval_slots(actual_runtime_slots)
        group = planner.next_group(
            vehicle_type=resolved_type.value if resolved_type is not None else None,
            known_slots=actual_runtime_slots,
            ask_counts=ask_counts,
        )
        actual_next_group = [EvalSlotName(slot.value) for slot in group]
        actual_question: str | None = None
        if group:
            retry = any(ask_counts.get(slot.value, 0) > 0 for slot in group)
            closed_group = retry and is_non_answer(turn.user_message)
            actual_question = planner.question_for_group(slots=group, retry=retry, closed=closed_group)
            for slot in group:
                ask_counts[slot.value] = ask_counts.get(slot.value, 0) + 1
        else:
            field = planner.next_field(
                vehicle_type=resolved_type.value if resolved_type is not None else None,
                known_slots=actual_runtime_slots,
                ask_counts=ask_counts,
            )
            if field is not None:
                retry_count = ask_counts.get(field.value, 0)
                actual_question = planner.question_for_turn(
                    slot=field,
                    retry_count=retry_count,
                    user_message=turn.user_message,
                    vehicle_mentions=extracted.vehicle_name_mentions,
                )
                if retry_count >= 1 and field.value not in actual_runtime_slots and turn.user_message.strip():
                    closed = planner.clarify_question(slot=field)
                    if closed is not None:
                        actual_question = closed
                ask_counts[field.value] = ask_counts.get(field.value, 0) + 1
        runtime_next_slot = next_slot(resolved_type, actual_runtime_slots)
        actual_next_slot = EvalSlotName(runtime_next_slot.value) if runtime_next_slot is not None else None
        actual_intents = [intent.value for intent in extracted.intents]
        if actual_next_slot is None and completed_at_turn is None:
            completed_at_turn = turn_number
        turn_results.append(
            TurnEvaluation(
                scenario_id=scenario.id,
                turn_number=turn_number,
                groups=scenario.groups,
                actual_slots=actual_slots,
                expected_slots=turn.expected_slots,
                forbidden_present=[slot for slot in turn.forbidden_slots if slot in actual_slots],
                actual_next_slot=actual_next_slot,
                expected_next_slot=turn.expected_next_slot,
                actual_next_group=actual_next_group,
                expected_next_group=turn.expected_next_group,
                actual_question=actual_question,
                expected_question=turn.expected_question,
                provided_slots=turn.provided_slots,
                correction_slots=turn.correction_slots,
                raw_intents=[intent.value for intent in capturing_llm.last_payload.intents],
                actual_intents=actual_intents,
                expected_intents=list(turn.expected_intents or []),
                forbidden_intents=turn.forbidden_intents,
                actual_decision=_decision(
                    actual_intents,
                    actual_next_slot,
                    _enum_value(getattr(capturing_llm.last_payload, "task", None)),
                ),
                raw_decision=_decision(
                    [intent.value for intent in capturing_llm.last_payload.intents],
                    actual_next_slot,
                ),
                expected_decision=turn.expected_decision or Decision.CLARIFY_INTENT,
                actual_vehicle_mentions=extracted.vehicle_name_mentions,
                expected_vehicle_mentions=turn.expected_vehicle_mentions,
                memory_context_used=bool(turn.memory_summary or turn.recent_messages),
            )
        )

    return ScenarioEvaluation(
        scenario_id=scenario.id,
        description=scenario.description,
        groups=scenario.groups,
        expects_completion=scenario.expects_completion,
        turns=turn_results,
        completed_at_turn=completed_at_turn,
    )


def _memory_context(turn: ConversationTurn, *, actual_slots: dict[EvalSlotName, SlotValue]) -> str:
    if not turn.memory_summary and not turn.recent_messages:
        return ""
    recent = tuple(
        ConversationMessage(
            role=item["role"],
            content=item["content"],
            turn_index=index,
        )
        for index, item in enumerate(turn.recent_messages, start=1)
    )
    summary = ConversationSummary(turn.memory_summary, 0) if turn.memory_summary else None
    return build_working_memory(
        slots={slot.value: value for slot, value in actual_slots.items()},
        summary=summary,
        recent_messages=recent,
        current_user_message=turn.user_message,
    )


async def run_conversation_dataset(
    dataset: ConversationDataset,
    *,
    live_llm: ExtractionLlm | None = None,
) -> ConversationRun:
    """Run every scenario offline, or against an explicitly supplied live LLM."""

    results: list[ScenarioEvaluation] = []
    for scenario in dataset.scenarios:
        llm: ExtractionLlm = live_llm or ScriptedLlm([turn.llm_payload for turn in scenario.turns])
        results.append(await _run_scenario(scenario, llm=llm))
    return ConversationRun(scenarios=results)
