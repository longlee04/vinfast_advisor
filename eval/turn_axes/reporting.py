"""Human- and machine-readable reports for four-axis evaluation runs."""

from __future__ import annotations

import json

from eval.turn_axes.models import TurnAxesMetricReport, TurnAxesRun


def render_json(run: TurnAxesRun, metrics: TurnAxesMetricReport) -> str:
    """Render complete details and aggregate metrics as stable JSON."""

    return json.dumps(
        {"metrics": metrics.model_dump(mode="json"), "run": run.model_dump(mode="json")},
        ensure_ascii=False,
        indent=2,
    )


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def render_markdown(run: TurnAxesRun, metrics: TurnAxesMetricReport) -> str:
    """Render a concise baseline plus every failing scenario."""

    lines = [
        "# Four-Axis Turn Understanding Evaluation",
        "",
        f"- Scenarios: {metrics.scenario_count}",
        f"- Turns: {metrics.turn_count}",
        f"- Dialogue-act accuracy: {_percent(metrics.dialogue_act_accuracy)}",
        f"- Task accuracy: {_percent(metrics.task_accuracy)}",
        f"- Primary-topic accuracy: {_percent(metrics.primary_topic_accuracy)}",
        f"- Secondary-topics accuracy: {_percent(metrics.secondary_topics_accuracy)}",
        f"- Severity accuracy: {_percent(metrics.severity_accuracy)}",
        f"- Human-requested accuracy: {_percent(metrics.human_requested_accuracy)}",
        f"- Joint match rate: {_percent(metrics.joint_match_rate)}",
        f"- Provider failure rate: {_percent(metrics.failure_rate)}",
        f"- Scenario pass rate: {_percent(metrics.scenario_pass_rate)}",
        "",
        "## Pass rate by group",
        "",
    ]
    lines.extend(f"- `{group}`: {_percent(rate)}" for group, rate in metrics.group_pass_rates.items())
    failures = [scenario for scenario in run.scenarios if not scenario.passed]
    lines.extend(["", "## Failing scenarios", ""])
    if not failures:
        lines.append("None.")
    for scenario in failures:
        lines.append(f"### {scenario.scenario_id} — {scenario.description}")
        for turn in scenario.turns:
            if turn.passed:
                continue
            lines.extend(
                [
                    f"- Turn {turn.turn_number}: {turn.user_message}",
                    f"  - expected: `{turn.expected.model_dump(mode='json')}`",
                    f"  - actual: `{turn.actual.model_dump(mode='json') if turn.actual else None}`",
                    f"  - failure reason: `{turn.failure_reason}`",
                ]
            )
    return "\n".join(lines) + "\n"
