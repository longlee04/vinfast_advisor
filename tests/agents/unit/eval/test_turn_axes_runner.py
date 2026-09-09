"""End-to-end offline checks for the four-axis turn-understanding path."""

import pytest

from eval.turn_axes.loader import load_turn_axes_dataset
from eval.turn_axes.metrics import calculate_metrics
from scripts.evaluate_turn_axes import (
    disable_live_tracing,
    live_eval_enabled,
    select_scenarios,
)
from scripts.turn_axes_runner import run_turn_axes_dataset


@pytest.mark.agent_eval
@pytest.mark.asyncio
async def test_offline_golden_dataset_passes_without_network_calls() -> None:
    run = await run_turn_axes_dataset(load_turn_axes_dataset())
    metrics = calculate_metrics(run)

    assert metrics.scenario_count >= 8
    assert metrics.scenario_pass_rate == 1.0
    assert metrics.failure_rate == pytest.approx(1 / metrics.turn_count)
    assert metrics.joint_match_rate == pytest.approx((metrics.turn_count - 1) / metrics.turn_count)
    # Ca đầu ra hỏng (TA008) là failed case nên trượt cả sáu trục.
    assert metrics.dialogue_act_accuracy == pytest.approx((metrics.turn_count - 1) / metrics.turn_count)
    assert metrics.task_accuracy == pytest.approx((metrics.turn_count - 1) / metrics.turn_count)
    assert metrics.primary_topic_accuracy == pytest.approx((metrics.turn_count - 1) / metrics.turn_count)
    assert metrics.secondary_topics_accuracy == pytest.approx((metrics.turn_count - 1) / metrics.turn_count)
    assert metrics.severity_accuracy == pytest.approx((metrics.turn_count - 1) / metrics.turn_count)
    assert metrics.human_requested_accuracy == pytest.approx((metrics.turn_count - 1) / metrics.turn_count)


@pytest.mark.agent_eval
@pytest.mark.asyncio
async def test_malformed_output_is_recorded_as_failed_case_not_silently_dropped() -> None:
    run = await run_turn_axes_dataset(load_turn_axes_dataset())
    malformed = [
        turn for scenario in run.scenarios for turn in scenario.turns if turn.expected.expect_failure is not None
    ]

    assert len(malformed) == 1
    turn = malformed[0]
    assert turn.failed is True
    assert turn.failure_reason == "invalid_llm_output"
    assert turn.passed is True, "expected failure recorded correctly is a pass"


@pytest.mark.agent_eval
@pytest.mark.asyncio
async def test_mixed_complaint_question_keeps_both_axes() -> None:
    run = await run_turn_axes_dataset(load_turn_axes_dataset())
    mixed = next(turn for scenario in run.scenarios for turn in scenario.turns if "Đắt quá" in turn.user_message)

    assert mixed.actual is not None
    assert mixed.actual.dialogue_act.value == "COMPLAIN"
    assert mixed.actual.task is not None
    assert mixed.actual.primary_topic.value == "PRICE_TCO"
    assert mixed.passed is True


@pytest.mark.agent_eval
@pytest.mark.asyncio
async def test_safety_false_positive_stays_normal_severity() -> None:
    run = await run_turn_axes_dataset(load_turn_axes_dataset())
    question = next(turn for scenario in run.scenarios for turn in scenario.turns if "bốc cháy" in turn.user_message)

    assert question.actual is not None
    assert question.actual.severity.value == "NORMAL"
    assert question.passed is True


@pytest.mark.agent_eval
@pytest.mark.asyncio
async def test_topic_cardinality_is_truncated_to_three_secondaries() -> None:
    run = await run_turn_axes_dataset(load_turn_axes_dataset())
    truncated = next(
        turn for scenario in run.scenarios for turn in scenario.turns if len(turn.expected.secondary_topics) == 3
    )

    assert truncated.actual is not None
    assert len(truncated.actual.secondary_topics) == 3
    assert truncated.passed is True


@pytest.mark.agent_eval
@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, False),
        ({"RUN_AGENT_EVAL": "false"}, False),
        ({"RUN_AGENT_EVAL": "0"}, False),
        ({"RUN_AGENT_EVAL": "1"}, True),
    ],
)
def test_live_evaluation_requires_explicit_opt_in(environment: dict[str, str], expected: bool) -> None:
    assert live_eval_enabled(environment) is expected


@pytest.mark.agent_eval
def test_live_eval_can_select_a_small_critical_subset() -> None:
    dataset = load_turn_axes_dataset()
    selected = select_scenarios(dataset, [dataset.scenarios[0].id])

    assert [scenario.id for scenario in selected.scenarios] == [dataset.scenarios[0].id]


@pytest.mark.agent_eval
def test_live_eval_rejects_unknown_scenario_ids() -> None:
    with pytest.raises(ValueError, match="TA999"):
        select_scenarios(load_turn_axes_dataset(), ["TA999"])


@pytest.mark.agent_eval
def test_live_eval_disables_external_tracing_in_its_process() -> None:
    environment = {"LANGCHAIN_TRACING_V2": "true", "LANGSMITH_TRACING": "true"}

    disable_live_tracing(environment)

    assert environment == {
        "LANGCHAIN_TRACING_V2": "false",
        "LANGSMITH_TRACING": "false",
    }
