"""Coverage and schema checks for the four-axis turn-understanding dataset."""

import pytest

from eval.turn_axes.loader import load_turn_axes_dataset
from src.agents.domain.values import DialogueAct, IntentType, Severity, Topic


def test_dataset_covers_every_required_vietnamese_case_group() -> None:
    dataset = load_turn_axes_dataset()
    groups = {group for scenario in dataset.scenarios for group in scenario.groups}

    assert len(dataset.scenarios) >= 8
    assert {
        "mixed",
        "human_request",
        "safety",
        "topic_cardinality",
        "malformed",
        "legacy",
    } <= groups


def test_dataset_has_the_mixed_complaint_question_case() -> None:
    dataset = load_turn_axes_dataset()
    mixed = [
        scenario
        for scenario in dataset.scenarios
        if "mixed" in scenario.groups and "Đắt quá" in scenario.turns[0].user_message
    ]

    assert len(mixed) >= 1
    turn = mixed[0].turns[0]
    assert turn.expected.dialogue_act is DialogueAct.COMPLAIN
    assert turn.expected.task is not None
    assert turn.expected.primary_topic is Topic.PRICE_TCO


def test_dataset_has_a_semantic_human_request_case() -> None:
    dataset = load_turn_axes_dataset()
    human = [
        scenario
        for scenario in dataset.scenarios
        if "human_request" in scenario.groups and "tư vấn viên" in scenario.turns[0].user_message
    ]

    assert len(human) >= 1
    turn = human[0].turns[0]
    assert turn.expected.task is IntentType.HUMAN_REQUEST
    assert turn.expected.human_requested is True


def test_dataset_has_a_safety_false_positive_and_a_true_positive() -> None:
    dataset = load_turn_axes_dataset()
    safety = [scenario for scenario in dataset.scenarios if "safety" in scenario.groups]

    assert len(safety) >= 2
    false_positive = next(scenario for scenario in safety if "bốc cháy" in scenario.turns[0].user_message)
    true_positive = next(scenario for scenario in safety if "bốc khói" in scenario.turns[0].user_message)
    assert false_positive.turns[0].expected.severity is Severity.NORMAL
    assert true_positive.turns[0].expected.severity is Severity.CRITICAL


def test_dataset_exercises_topic_cardinality_within_and_beyond_the_limit() -> None:
    dataset = load_turn_axes_dataset()
    cardinality = [scenario for scenario in dataset.scenarios if "topic_cardinality" in scenario.groups]

    assert len(cardinality) >= 2
    assert any(len(turn.expected.secondary_topics) <= 3 for scenario in cardinality for turn in scenario.turns)
    assert any(len(turn.expected.secondary_topics) == 3 for scenario in cardinality for turn in scenario.turns)


def test_dataset_has_a_malformed_output_case_that_expects_a_recorded_failure() -> None:
    dataset = load_turn_axes_dataset()
    malformed = [scenario for scenario in dataset.scenarios if "malformed" in scenario.groups]

    assert len(malformed) >= 1
    assert any(turn.expected.expect_failure is not None for scenario in malformed for turn in scenario.turns)


def test_dataset_has_a_legacy_payload_case_with_safe_defaults() -> None:
    dataset = load_turn_axes_dataset()
    legacy = [
        scenario
        for scenario in dataset.scenarios
        if "legacy" in scenario.groups and scenario.turns[0].llm_payload.task is None
    ]

    assert len(legacy) >= 1
    turn = legacy[0].turns[0]
    assert turn.expected.dialogue_act is DialogueAct.UNKNOWN
    assert turn.expected.task is None
    assert turn.expected.primary_topic is Topic.OTHER
    assert turn.expected.severity is Severity.NORMAL
    assert turn.expected.human_requested is False


def test_every_turn_declares_all_axis_expectations() -> None:
    dataset = load_turn_axes_dataset()

    for scenario in dataset.scenarios:
        for turn in scenario.turns:
            assert turn.expected.dialogue_act is not None
            assert turn.expected.primary_topic is not None
            assert turn.expected.severity is not None
            assert turn.expected.human_requested is not None
            assert all(isinstance(topic, Topic) for topic in turn.expected.secondary_topics)


def test_dataset_rejects_duplicate_scenario_ids() -> None:
    from eval.turn_axes.models import (
        TurnAxesDataset,
        TurnAxesExpectation,
        TurnAxesScenario,
        TurnAxesTurn,
    )
    from src.agents.domain.values import DialogueAct, IntentType, Topic

    turn = TurnAxesTurn(
        user_message="cau hoi",
        expected=TurnAxesExpectation(
            dialogue_act=DialogueAct.REQUEST,
            task=IntentType.VEHICLE_INFO,
            primary_topic=Topic.VEHICLE,
        ),
    )
    scenario = TurnAxesScenario(id="TA001", description="dup", groups=["sample"], turns=[turn])

    with pytest.raises(ValueError, match="TA001"):
        TurnAxesDataset(version=1, scenarios=[scenario, scenario])
