"""Exact formula tests for conversation-evaluation metrics."""

import pytest

from eval.conversation.metrics import calculate_metrics
from eval.conversation.models import (
    ConversationRun,
    Decision,
    ScenarioEvaluation,
    SlotName,
    TurnEvaluation,
)


def test_metrics_count_false_fills_redundancy_corrections_and_completion() -> None:
    first_turn = TurnEvaluation(
        scenario_id="SC900",
        turn_number=1,
        groups=["sample"],
        actual_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.PASSENGER_COUNT: 7,
        },
        expected_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.PASSENGER_COUNT: 5,
        },
        forbidden_present=[],
        actual_next_slot=SlotName.PASSENGER_COUNT,
        expected_next_slot=SlotName.PASSENGER_COUNT,
        provided_slots=[SlotName.PASSENGER_COUNT],
        correction_slots=[SlotName.PASSENGER_COUNT],
        raw_intents=[],
        actual_intents=[],
        expected_intents=["ADVISORY"],
        forbidden_intents=[],
        actual_decision=Decision.CLARIFY_INTENT,
        raw_decision=Decision.CLARIFY_INTENT,
        expected_decision=Decision.ASK,
    )
    second_turn = TurnEvaluation(
        scenario_id="SC900",
        turn_number=2,
        groups=["sample"],
        actual_slots={SlotName.VEHICLE_TYPE: "CAR"},
        expected_slots={SlotName.VEHICLE_TYPE: "CAR"},
        forbidden_present=[],
        actual_next_slot=None,
        expected_next_slot=None,
        provided_slots=[],
        correction_slots=[],
        raw_intents=["CATALOG_LOOKUP"],
        actual_intents=["CATALOG_LOOKUP"],
        expected_intents=["CATALOG_LOOKUP"],
        forbidden_intents=[],
        actual_decision=Decision.LOOKUP,
        raw_decision=Decision.LOOKUP,
        expected_decision=Decision.LOOKUP,
    )
    run = ConversationRun(
        scenarios=[
            ScenarioEvaluation(
                scenario_id="SC900",
                description="metric sample",
                groups=["sample"],
                expects_completion=True,
                turns=[first_turn, second_turn],
                completed_at_turn=2,
            )
        ]
    )

    metrics = calculate_metrics(run)

    assert metrics.slot_precision == pytest.approx(2 / 3)
    assert metrics.slot_recall == pytest.approx(2 / 3)
    assert metrics.false_fill_rate == pytest.approx(1 / 3)
    assert metrics.redundant_question_rate == 1.0
    assert metrics.next_question_accuracy == 1.0
    assert metrics.correction_accuracy == 0.0
    assert metrics.completion_rate == 1.0
    assert metrics.average_turns_to_completion == 2.0
    assert metrics.scenario_pass_rate == 0.0
    assert metrics.group_pass_rates == {"sample": 0.0}
    assert metrics.intent_exact_match == 0.5
    assert metrics.raw_intent_exact_match == 0.5
    assert metrics.intent_false_negative_rate == 0.5
    assert metrics.intent_false_positive_rate == 0.0
    assert metrics.decision_accuracy == 0.5
    assert metrics.raw_decision_accuracy == 0.5
    assert metrics.referent_resolution_accuracy is None
    assert metrics.false_memory_carry_over_rate is None
    assert metrics.context_carry_over_accuracy is None


def test_empty_run_reports_undefined_ratios_instead_of_fake_zeroes() -> None:
    metrics = calculate_metrics(ConversationRun(scenarios=[]))

    assert metrics.scenario_count == 0
    assert metrics.turn_count == 0
    assert metrics.slot_precision is None
    assert metrics.slot_recall is None
    assert metrics.false_fill_rate is None
    assert metrics.redundant_question_rate is None
    assert metrics.next_question_accuracy is None
    assert metrics.correction_accuracy is None
    assert metrics.completion_rate is None
    assert metrics.average_turns_to_completion is None
    assert metrics.scenario_pass_rate is None
    assert metrics.intent_exact_match is None
    assert metrics.raw_intent_exact_match is None
    assert metrics.intent_false_negative_rate is None
    assert metrics.intent_false_positive_rate is None
    assert metrics.decision_accuracy is None
    assert metrics.raw_decision_accuracy is None
    assert metrics.referent_resolution_accuracy is None
    assert metrics.false_memory_carry_over_rate is None
    assert metrics.context_carry_over_accuracy is None
