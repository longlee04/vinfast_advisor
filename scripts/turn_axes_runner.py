"""Run four-axis eval fixtures through production extraction code.

Kế thừa đúng runner của eval slot (`scripts/slot_conversation_runner.py`): cùng
`InMemorySessions` + `EvaluationUnitOfWork`, cùng `SlotExtractionServiceImpl`.
Chỉ khác schema — so sánh theo bốn trục thay vì slot/intent — và thêm bắt lỗi
provider: đầu ra hỏng/timeout phải thành failed case, không âm thầm loại.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import ValidationError

from eval.turn_axes.models import (
    TurnAxesDataset,
    TurnAxesEvaluation,
    TurnAxesResult,
    TurnAxesRun,
    TurnAxesScenario,
    TurnAxesScenarioEvaluation,
)
from scripts.slot_conversation_runner import EvaluationUnitOfWork, InMemorySessions
from src.agents.contracts import LLMExtractionPayload
from src.agents.services.slot_extraction import SlotExtractionServiceImpl


class TurnAxesLlm(Protocol):
    """Narrow LLM surface used by the four-axis evaluation runner."""

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload: ...


@dataclass
class ScriptedTurnAxesLlm:
    """Return dataset payloads in order; never call a network service.

    Trả dict THÔ (chưa validate) để `SlotExtractionServiceImpl` tự validate —
    đúng như production nhận JSON từ mô hình. Ca đầu ra hỏng vì vậy nổ
    `ValidationError` đúng chỗ production sẽ nổ.
    """

    payloads: Sequence[dict[str, object]]
    calls: int = field(default=0)

    async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
        if self.calls >= len(self.payloads):
            raise RuntimeError("scripted LLM đã hết payload")
        payload = self.payloads[self.calls]
        self.calls += 1
        return LLMExtractionPayload.model_validate(payload)


def _failure_reason(error: Exception) -> str:
    """Phân loại lỗi provider thành nhãn ổn định cho báo cáo."""

    if isinstance(error, ValidationError):
        return "invalid_llm_output"
    if isinstance(error, TimeoutError):
        return "provider_timeout"
    return "provider_error"


async def _run_scenario(scenario: TurnAxesScenario, *, llm: TurnAxesLlm) -> TurnAxesScenarioEvaluation:
    sessions = InMemorySessions()
    service = SlotExtractionServiceImpl(  # type: ignore[arg-type]
        llm, EvaluationUnitOfWork(sessions)
    )
    turn_results: list[TurnAxesEvaluation] = []

    for turn_number, turn in enumerate(scenario.turns, start=1):
        actual: TurnAxesResult | None = None
        failure_reason: str | None = None
        # Biên eval: MỌI lỗi provider (timeout, đầu ra hỏng) phải thành failed
        # case để báo cáo, không được làm chết cả lượt chạy hay bị bỏ lặng.
        try:
            extracted = await service.extract(
                session_id=scenario.id,
                customer_id="offline-eval",
                vehicle_type=None,
                user_message=turn.user_message,
            )
            actual = TurnAxesResult(
                dialogue_act=extracted.dialogue_act,
                task=extracted.task,
                primary_topic=extracted.primary_topic,
                secondary_topics=extracted.secondary_topics,
                severity=extracted.severity,
                human_requested=extracted.human_requested,
            )
        except Exception as error:
            failure_reason = _failure_reason(error)
        turn_results.append(
            TurnAxesEvaluation(
                scenario_id=scenario.id,
                turn_number=turn_number,
                user_message=turn.user_message,
                actual=actual,
                expected=turn.expected,
                failure_reason=failure_reason,
            )
        )

    return TurnAxesScenarioEvaluation(
        scenario_id=scenario.id,
        description=scenario.description,
        groups=scenario.groups,
        turns=turn_results,
    )


async def run_turn_axes_dataset(
    dataset: TurnAxesDataset,
    *,
    live_llm: TurnAxesLlm | None = None,
) -> TurnAxesRun:
    """Run every scenario offline, or against an explicitly supplied live LLM."""

    results: list[TurnAxesScenarioEvaluation] = []
    for scenario in dataset.scenarios:
        llm: TurnAxesLlm = live_llm or ScriptedTurnAxesLlm([turn.llm_payload.model_dump() for turn in scenario.turns])
        results.append(await _run_scenario(scenario, llm=llm))
    return TurnAxesRun(scenarios=results)
