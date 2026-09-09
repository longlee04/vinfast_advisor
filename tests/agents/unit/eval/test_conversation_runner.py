"""End-to-end offline checks for the real extraction and slot-policy path."""

import pytest

from eval.conversation.loader import load_conversation_dataset
from eval.conversation.metrics import calculate_metrics
from scripts.evaluate_slot_conversations import (
    disable_live_tracing,
    live_eval_enabled,
    select_scenarios,
)
from scripts.slot_conversation_runner import run_conversation_dataset


@pytest.mark.asyncio
async def test_offline_golden_dataset_passes_without_network_calls() -> None:
    run = await run_conversation_dataset(load_conversation_dataset())
    metrics = calculate_metrics(run)

    assert metrics.scenario_count >= 40
    assert metrics.scenario_pass_rate == 1.0
    assert metrics.slot_precision == 1.0
    assert metrics.slot_recall == 1.0
    assert metrics.false_fill_rate == 0.0
    assert metrics.redundant_question_rate == 0.0
    assert metrics.next_question_accuracy == 1.0
    assert metrics.intent_exact_match == 1.0
    assert metrics.intent_false_negative_rate == 0.0
    assert metrics.intent_false_positive_rate == 0.0
    assert metrics.decision_accuracy == 1.0
    assert metrics.referent_resolution_accuracy == 1.0
    assert metrics.context_carry_over_accuracy == 1.0
    assert metrics.false_memory_carry_over_rate == 0.0

    hybrid = next(scenario for scenario in run.scenarios if scenario.scenario_id == "SC041")
    assert hybrid.turns[0].raw_intents == ["CATALOG_LOOKUP"]
    assert hybrid.turns[0].actual_intents == ["ADVISORY", "CATALOG_LOOKUP"]

    empty_raw = next(scenario for scenario in run.scenarios if scenario.scenario_id == "SC060")
    assert empty_raw.turns[0].raw_decision.value == "CLARIFY_INTENT"
    assert empty_raw.turns[0].actual_decision.value == "LOOKUP"

    extra_raw = next(scenario for scenario in run.scenarios if scenario.scenario_id == "SC061")
    assert extra_raw.turns[0].raw_decision.value == "HYBRID"
    assert extra_raw.turns[0].actual_decision.value == "LOOKUP"


def test_extraction_payload_mirrors_purpose_bucket_field() -> None:
    from eval.conversation.models import ExtractionPayload
    from src.agents.contracts import LLMExtractionPayload

    fixture = ExtractionPayload(purpose_bucket="family")
    payload = LLMExtractionPayload.model_validate(fixture.model_dump())

    assert payload.purpose_bucket.value == "family"


@pytest.mark.parametrize(
    ("environment", "expected"),
    [({}, False), ({"AGENT_SLOT_EVAL_LIVE": "false"}, False), ({"AGENT_SLOT_EVAL_LIVE": "1"}, True)],
)
def test_live_evaluation_requires_explicit_opt_in(environment: dict[str, str], expected: bool) -> None:
    assert live_eval_enabled(environment) is expected


def test_live_eval_can_select_a_small_critical_subset() -> None:
    selected = select_scenarios(load_conversation_dataset(), ["SC041", "SC046"])

    assert [scenario.id for scenario in selected.scenarios] == ["SC041", "SC046"]


def test_live_eval_rejects_unknown_scenario_ids() -> None:
    with pytest.raises(ValueError, match="SC999"):
        select_scenarios(load_conversation_dataset(), ["SC999"])


def test_live_eval_disables_external_tracing_in_its_process() -> None:
    environment = {"LANGCHAIN_TRACING_V2": "true", "LANGSMITH_TRACING": "true"}

    disable_live_tracing(environment)

    assert environment == {
        "LANGCHAIN_TRACING_V2": "false",
        "LANGSMITH_TRACING": "false",
    }
