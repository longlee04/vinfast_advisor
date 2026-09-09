"""Confusion, quality, latency, cost, and merge-gate calculations."""

from collections import Counter

from eval.bottleneck.models import (
    DetectionStatus,
    EvalLabel,
    EvalMetrics,
    EvalObservation,
    GateFailure,
    GateResult,
    GateThresholds,
    LabelMetrics,
    TokenPrices,
)


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def calculate_metrics(observations: list[EvalObservation], prices: TokenPrices) -> EvalMetrics:
    confusion = {expected: {predicted: 0 for predicted in EvalLabel} for expected in EvalLabel}
    statuses = Counter({status: 0 for status in DetectionStatus})
    for observation in observations:
        statuses[observation.status] += 1
        if observation.predicted_label is not None:
            confusion[observation.expected_label][observation.predicted_label] += 1

    per_label: dict[EvalLabel, LabelMetrics] = {}
    for label in EvalLabel:
        true_positive = confusion[label][label]
        predicted = sum(confusion[expected][label] for expected in EvalLabel)
        support = sum(confusion[label].values())
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = LabelMetrics(precision=precision, recall=recall, f1=f1, support=support)

    latencies = [observation.latency_ms for observation in observations]
    input_tokens = sum(observation.input_tokens for observation in observations)
    output_tokens = sum(observation.output_tokens for observation in observations)
    cost = (input_tokens * prices.input_usd_per_million + output_tokens * prices.output_usd_per_million) / 1_000_000
    return EvalMetrics(
        case_count=len(observations),
        per_label=per_label,
        macro_f1=sum(metric.f1 for metric in per_label.values()) / len(EvalLabel),
        confusion=confusion,
        status_counts=dict(statuses),
        p50_latency_ms=_percentile(latencies, 0.50) if latencies else 0,
        p95_latency_ms=_percentile(latencies, 0.95) if latencies else 0,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        invalid_payload_count=sum(item.invalid_payload for item in observations),
    )


def evaluate_gates(metrics: EvalMetrics, thresholds: GateThresholds) -> GateResult:
    failures: list[GateFailure] = []
    checks = (
        ("macro_f1", metrics.macro_f1, thresholds.macro_f1, False),
        (
            "price_precision",
            metrics.per_label[EvalLabel.PRICE].precision,
            thresholds.price_precision,
            False,
        ),
        ("invalid_payload", float(metrics.invalid_payload_count), 0.0, True),
        ("p95_latency", float(metrics.p95_latency_ms), float(thresholds.p95_latency_ms), True),
    )
    for code, actual, threshold, upper_bound in checks:
        failed = actual > threshold if upper_bound else actual < threshold
        if failed:
            failures.append(GateFailure(code=code, actual=actual, threshold=threshold))
    return GateResult(passed=not failures, failures=tuple(failures))
