"""Human- and machine-readable reports for conversation evaluation runs."""

from __future__ import annotations

import json

from eval.conversation.models import ConversationRun, MetricReport


def render_json(run: ConversationRun, metrics: MetricReport) -> str:
    """Render complete details and aggregate metrics as stable JSON."""

    return json.dumps(
        {"metrics": metrics.model_dump(mode="json"), "run": run.model_dump(mode="json")},
        ensure_ascii=False,
        indent=2,
    )


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def render_markdown(run: ConversationRun, metrics: MetricReport) -> str:
    """Render a concise baseline plus every failing scenario."""

    lines = [
        "# Slot Conversation Evaluation",
        "",
        f"- Scenarios: {metrics.scenario_count}",
        f"- Turns: {metrics.turn_count}",
        f"- Slot precision: {_percent(metrics.slot_precision)}",
        f"- Slot recall: {_percent(metrics.slot_recall)}",
        f"- False-fill rate: {_percent(metrics.false_fill_rate)}",
        f"- Redundant-question rate: {_percent(metrics.redundant_question_rate)}",
        f"- Next-question accuracy: {_percent(metrics.next_question_accuracy)}",
        f"- Correction accuracy: {_percent(metrics.correction_accuracy)}",
        f"- Completion rate: {_percent(metrics.completion_rate)}",
        "- Average turns to completion: "
        + (
            "N/A"
            if metrics.average_turns_to_completion is None
            else f"{metrics.average_turns_to_completion:.2f}"
        ),
        f"- Scenario pass rate: {_percent(metrics.scenario_pass_rate)}",
        f"- Raw intent exact match: {_percent(metrics.raw_intent_exact_match)}",
        f"- Normalized intent exact match: {_percent(metrics.intent_exact_match)}",
        f"- Intent false-negative rate: {_percent(metrics.intent_false_negative_rate)}",
        f"- Intent false-positive rate: {_percent(metrics.intent_false_positive_rate)}",
        f"- Decision accuracy: {_percent(metrics.decision_accuracy)}",
        f"- Raw decision accuracy: {_percent(metrics.raw_decision_accuracy)}",
        f"- Referent resolution accuracy: {_percent(metrics.referent_resolution_accuracy)}",
        f"- Context carry-over accuracy: {_percent(metrics.context_carry_over_accuracy)}",
        f"- False memory carry-over rate: {_percent(metrics.false_memory_carry_over_rate)}",
        "",
        "## Pass rate by group",
        "",
    ]
    lines.extend(
        f"- `{group}`: {_percent(rate)}" for group, rate in metrics.group_pass_rates.items()
    )
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
                    f"- Turn {turn.turn_number}",
                    f"  - expected slots: `{turn.expected_slots}`",
                    f"  - actual slots: `{turn.actual_slots}`",
                    f"  - expected next: `{turn.expected_next_slot}`",
                    f"  - actual next: `{turn.actual_next_slot}`",
                    f"  - expected intents: `{turn.expected_intents}`",
                    f"  - raw LLM intents: `{turn.raw_intents}`",
                    f"  - actual intents: `{turn.actual_intents}`",
                    f"  - expected decision: `{turn.expected_decision}`",
                    f"  - actual decision: `{turn.actual_decision}`",
                    f"  - raw decision: `{turn.raw_decision}`",
                    f"  - expected vehicle mentions: `{turn.expected_vehicle_mentions}`",
                    f"  - actual vehicle mentions: `{turn.actual_vehicle_mentions}`",
                ]
            )
    return "\n".join(lines) + "\n"
