"""Bottleneck classifier confusion, gate, latency, and cost tests."""

import pytest

from eval.bottleneck.metrics import calculate_metrics, evaluate_gates
from eval.bottleneck.models import (
    EvalLabel,
    EvalObservation,
    GateThresholds,
    TokenPrices,
)


def _observation(expected: EvalLabel, predicted: EvalLabel, latency_ms: int = 100) -> EvalObservation:
    return EvalObservation(
        case_id=f"{expected}-{predicted}-{latency_ms}",
        expected_label=expected,
        predicted_label=predicted,
        status="NONE" if predicted is EvalLabel.NONE else "DETECTED",
        latency_ms=latency_ms,
        input_tokens=1_000,
        output_tokens=500,
        invalid_payload=False,
    )


def test_metrics_calculate_confusion_per_label_macro_latency_status_and_exact_cost() -> None:
    # Given
    observations = [
        _observation(EvalLabel.PRICE, EvalLabel.PRICE, 100),
        _observation(EvalLabel.PRICE, EvalLabel.NONE, 200),
        _observation(EvalLabel.NONE, EvalLabel.PRICE, 300),
        _observation(EvalLabel.NONE, EvalLabel.NONE, 4_000),
    ]
    prices = TokenPrices(input_usd_per_million=2.0, output_usd_per_million=8.0)

    # When
    metrics = calculate_metrics(observations, prices)

    # Then
    assert metrics.per_label[EvalLabel.PRICE].precision == pytest.approx(0.5)
    assert metrics.per_label[EvalLabel.PRICE].recall == pytest.approx(0.5)
    assert metrics.per_label[EvalLabel.PRICE].f1 == pytest.approx(0.5)
    assert metrics.confusion[EvalLabel.PRICE][EvalLabel.NONE] == 1
    assert metrics.macro_f1 == pytest.approx(0.2)
    assert metrics.status_counts == {"DETECTED": 2, "NONE": 2, "UNAVAILABLE": 0}
    assert metrics.p50_latency_ms == 200
    assert metrics.p95_latency_ms == 4_000
    assert metrics.input_tokens == 4_000
    assert metrics.output_tokens == 2_000
    assert metrics.estimated_cost_usd == pytest.approx(0.024)


def test_gates_fail_for_quality_price_invalid_payload_and_latency() -> None:
    # Given
    observations = [
        _observation(EvalLabel.PRICE, EvalLabel.NONE, 3_001),
        EvalObservation(
            case_id="invalid",
            expected_label=EvalLabel.NONE,
            predicted_label=None,
            status="UNAVAILABLE",
            latency_ms=100,
            input_tokens=0,
            output_tokens=0,
            invalid_payload=True,
        ),
    ]
    metrics = calculate_metrics(observations, TokenPrices())

    # When
    gates = evaluate_gates(metrics, GateThresholds())

    # Then
    assert gates.passed is False
    assert {failure.code for failure in gates.failures} == {
        "macro_f1",
        "price_precision",
        "invalid_payload",
        "p95_latency",
    }
