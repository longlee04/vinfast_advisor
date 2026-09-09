"""Pure metric calculations for four-axis turn-understanding evaluation results."""

from __future__ import annotations

from collections import defaultdict

from eval.turn_axes.models import TurnAxesMetricReport, TurnAxesRun, TurnAxesScenarioEvaluation


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def calculate_metrics(run: TurnAxesRun) -> TurnAxesMetricReport:
    """Calculate per-axis, joint-match, and failure metrics without hiding empty samples."""

    turns = run.turns
    groups: dict[str, list[TurnAxesScenarioEvaluation]] = defaultdict(list)
    for scenario in run.scenarios:
        for group in scenario.groups:
            groups[group].append(scenario)

    return TurnAxesMetricReport(
        scenario_count=len(run.scenarios),
        turn_count=len(turns),
        dialogue_act_accuracy=_ratio(sum(turn.dialogue_act_match for turn in turns), len(turns)),
        task_accuracy=_ratio(sum(turn.task_match for turn in turns), len(turns)),
        primary_topic_accuracy=_ratio(sum(turn.primary_topic_match for turn in turns), len(turns)),
        secondary_topics_accuracy=_ratio(sum(turn.secondary_topics_match for turn in turns), len(turns)),
        severity_accuracy=_ratio(sum(turn.severity_match for turn in turns), len(turns)),
        human_requested_accuracy=_ratio(sum(turn.human_requested_match for turn in turns), len(turns)),
        joint_match_rate=_ratio(sum(turn.joint_match for turn in turns), len(turns)),
        failure_rate=_ratio(sum(turn.failed for turn in turns), len(turns)),
        scenario_pass_rate=_ratio(sum(scenario.passed for scenario in run.scenarios), len(run.scenarios)),
        group_pass_rates={
            group: _ratio(sum(scenario.passed for scenario in scenarios), len(scenarios))
            for group, scenarios in sorted(groups.items())
        },
    )
