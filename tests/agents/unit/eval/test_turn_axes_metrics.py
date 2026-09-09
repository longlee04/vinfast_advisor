"""Exact formula tests for four-axis turn-understanding metrics."""

import pytest

from eval.turn_axes.metrics import calculate_metrics
from eval.turn_axes.models import (
    TurnAxesEvaluation,
    TurnAxesExpectation,
    TurnAxesResult,
    TurnAxesRun,
    TurnAxesScenarioEvaluation,
)
from src.agents.domain.values import DialogueAct, IntentType, Severity, Topic


def _expected() -> TurnAxesExpectation:
    return TurnAxesExpectation(
        dialogue_act=DialogueAct.REQUEST,
        task=IntentType.PRICE_TCO_QUERY,
        primary_topic=Topic.PRICE_TCO,
        secondary_topics=(),
        severity=Severity.NORMAL,
        human_requested=False,
    )


def _result(
    *,
    dialogue_act: DialogueAct = DialogueAct.REQUEST,
    task: IntentType | None = IntentType.PRICE_TCO_QUERY,
    primary_topic: Topic = Topic.PRICE_TCO,
    secondary_topics: tuple[Topic, ...] = (),
    severity: Severity = Severity.NORMAL,
    human_requested: bool = False,
) -> TurnAxesResult:
    return TurnAxesResult(
        dialogue_act=dialogue_act,
        task=task,
        primary_topic=primary_topic,
        secondary_topics=secondary_topics,
        severity=severity,
        human_requested=human_requested,
    )


def _turn(turn_number: int, *, actual: TurnAxesResult | None, failure_reason: str | None = None) -> TurnAxesEvaluation:
    return TurnAxesEvaluation(
        scenario_id="TA900",
        turn_number=turn_number,
        user_message="cau hoi",
        actual=actual,
        expected=_expected(),
        failure_reason=failure_reason,
    )


def test_metrics_report_each_axis_and_joint_match_separately() -> None:
    run = TurnAxesRun(
        scenarios=[
            TurnAxesScenarioEvaluation(
                scenario_id="TA900",
                description="metric sample",
                groups=["sample"],
                turns=[
                    _turn(1, actual=_result()),
                    _turn(2, actual=_result(dialogue_act=DialogueAct.COMPLAIN)),
                    _turn(3, actual=_result(task=IntentType.VEHICLE_INFO)),
                    _turn(4, actual=_result(primary_topic=Topic.VEHICLE)),
                    _turn(5, actual=_result(secondary_topics=(Topic.POLICY,))),
                    _turn(6, actual=_result(severity=Severity.ELEVATED)),
                    _turn(7, actual=_result(human_requested=True)),
                    _turn(8, actual=None, failure_reason="invalid_llm_output"),
                ],
            )
        ]
    )

    metrics = calculate_metrics(run)

    assert metrics.scenario_count == 1
    assert metrics.turn_count == 8
    # Turn 8 (failed) trượt cả sáu trục, nên mỗi trục có đúng 2 lượt trượt.
    assert metrics.dialogue_act_accuracy == pytest.approx(6 / 8)
    assert metrics.task_accuracy == pytest.approx(6 / 8)
    assert metrics.primary_topic_accuracy == pytest.approx(6 / 8)
    assert metrics.secondary_topics_accuracy == pytest.approx(6 / 8)
    assert metrics.severity_accuracy == pytest.approx(6 / 8)
    assert metrics.human_requested_accuracy == pytest.approx(6 / 8)
    assert metrics.joint_match_rate == pytest.approx(1 / 8)
    assert metrics.failure_rate == pytest.approx(1 / 8)
    assert metrics.scenario_pass_rate == 0.0
    assert metrics.group_pass_rates == {"sample": 0.0}


def test_expected_failure_still_counts_as_failed_turn_in_metrics() -> None:
    """A recorded provider failure is a failed case even when the dataset expects it."""
    expected = _expected().model_copy(update={"expect_failure": "invalid_llm_output"})
    turn = TurnAxesEvaluation(
        scenario_id="TA901",
        turn_number=1,
        user_message="cau hoi",
        actual=None,
        expected=expected,
        failure_reason="invalid_llm_output",
    )
    run = TurnAxesRun(
        scenarios=[
            TurnAxesScenarioEvaluation(
                scenario_id="TA901",
                description="expected failure",
                groups=["malformed"],
                turns=[turn],
            )
        ]
    )

    metrics = calculate_metrics(run)

    assert turn.passed is True, "expected failure recorded correctly is a pass"
    assert metrics.scenario_pass_rate == 1.0
    assert metrics.failure_rate == 1.0
    assert metrics.joint_match_rate == 0.0


def test_empty_run_reports_undefined_ratios_instead_of_fake_zeroes() -> None:
    metrics = calculate_metrics(TurnAxesRun(scenarios=[]))

    assert metrics.scenario_count == 0
    assert metrics.turn_count == 0
    assert metrics.dialogue_act_accuracy is None
    assert metrics.task_accuracy is None
    assert metrics.primary_topic_accuracy is None
    assert metrics.secondary_topics_accuracy is None
    assert metrics.severity_accuracy is None
    assert metrics.human_requested_accuracy is None
    assert metrics.joint_match_rate is None
    assert metrics.failure_rate is None
    assert metrics.scenario_pass_rate is None
    assert metrics.group_pass_rates == {}
