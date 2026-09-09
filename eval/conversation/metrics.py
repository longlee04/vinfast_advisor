"""Pure metric calculations for slot-conversation evaluation results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from eval.conversation.models import ConversationRun, MetricReport, ScenarioEvaluation


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _mean(values: Sequence[int]) -> float | None:
    return sum(values) / len(values) if values else None


def calculate_metrics(run: ConversationRun) -> MetricReport:
    """Calculate aggregate and per-group metrics without hiding empty samples."""

    turns = run.turns
    actual_slots = sum(len(turn.actual_slots) for turn in turns)
    expected_slots = sum(len(turn.expected_slots) for turn in turns)
    correct_slots = sum(turn.correct_slot_count for turn in turns)
    false_fills = sum(turn.false_fill_count for turn in turns)
    actual_questions = sum(1 for turn in turns if turn.actual_next_slot is not None)
    redundant_questions = sum(1 for turn in turns if turn.redundant_question)
    correct_next_questions = sum(1 for turn in turns if turn.next_question_correct)
    correction_count = sum(turn.correction_count for turn in turns)
    correct_corrections = sum(turn.correct_correction_count for turn in turns)
    expected_intents = sum(len(turn.expected_intents) for turn in turns)
    actual_intents = sum(len(turn.actual_intents) for turn in turns)
    missing_intents = sum(
        len(set(turn.expected_intents) - set(turn.actual_intents)) for turn in turns
    )
    unexpected_intents = sum(
        len(set(turn.actual_intents) - set(turn.expected_intents)) for turn in turns
    )
    referent_turns = [turn for turn in turns if turn.expected_vehicle_mentions]
    memory_turns = [turn for turn in turns if turn.memory_context_used]
    unexpected_mentions = sum(
        len(set(turn.actual_vehicle_mentions) - set(turn.expected_vehicle_mentions))
        for turn in turns
    )
    actual_mentions = sum(len(turn.actual_vehicle_mentions) for turn in turns)

    completion_targets = [scenario for scenario in run.scenarios if scenario.expects_completion]
    completed_targets = [
        scenario for scenario in completion_targets if scenario.completed_at_turn is not None
    ]
    completion_turns = [
        scenario.completed_at_turn
        for scenario in completed_targets
        if scenario.completed_at_turn is not None
    ]

    groups: dict[str, list[ScenarioEvaluation]] = defaultdict(list)
    for scenario in run.scenarios:
        for group in scenario.groups:
            groups[group].append(scenario)

    return MetricReport(
        scenario_count=len(run.scenarios),
        turn_count=len(turns),
        slot_precision=_ratio(correct_slots, actual_slots),
        slot_recall=_ratio(correct_slots, expected_slots),
        false_fill_rate=_ratio(false_fills, actual_slots),
        redundant_question_rate=_ratio(redundant_questions, actual_questions),
        next_question_accuracy=_ratio(correct_next_questions, len(turns)),
        correction_accuracy=_ratio(correct_corrections, correction_count),
        completion_rate=_ratio(len(completed_targets), len(completion_targets)),
        average_turns_to_completion=_mean(completion_turns),
        scenario_pass_rate=_ratio(sum(1 for scenario in run.scenarios if scenario.passed), len(run.scenarios)),
        group_pass_rates={
            group: _ratio(sum(1 for scenario in scenarios if scenario.passed), len(scenarios))
            for group, scenarios in sorted(groups.items())
        },
        raw_intent_exact_match=_ratio(
            sum(set(turn.raw_intents) == set(turn.expected_intents) for turn in turns),
            len(turns),
        ),
        intent_exact_match=_ratio(
            sum(set(turn.actual_intents) == set(turn.expected_intents) for turn in turns),
            len(turns),
        ),
        intent_false_negative_rate=_ratio(missing_intents, expected_intents),
        intent_false_positive_rate=_ratio(unexpected_intents, actual_intents),
        decision_accuracy=_ratio(
            sum(turn.actual_decision is turn.expected_decision for turn in turns), len(turns)
        ),
        raw_decision_accuracy=_ratio(
            sum(turn.raw_decision is turn.expected_decision for turn in turns), len(turns)
        ),
        referent_resolution_accuracy=_ratio(
            sum(
                set(turn.actual_vehicle_mentions) == set(turn.expected_vehicle_mentions)
                for turn in referent_turns
            ),
            len(referent_turns),
        ),
        false_memory_carry_over_rate=_ratio(unexpected_mentions, actual_mentions),
        context_carry_over_accuracy=_ratio(
            sum(
                set(turn.actual_vehicle_mentions) == set(turn.expected_vehicle_mentions)
                for turn in memory_turns
            ),
            len(memory_turns),
        ),
    )
