"""Execute bottleneck evaluation cases through injected detector."""

from eval.bottleneck.metrics import calculate_metrics, evaluate_gates
from eval.bottleneck.models import (
    BottleneckDataset,
    CaseDetector,
    EvalReport,
    GateThresholds,
    TokenPrices,
)


async def run_dataset(
    dataset: BottleneckDataset,
    detector: CaseDetector,
    *,
    prices: TokenPrices | None = None,
    thresholds: GateThresholds | None = None,
    model: str = "offline-fixture",
    prompt_version: str = "bottleneck-detection-v1",
) -> EvalReport:
    observations = [await detector.evaluate(case.id, case.text, case.expected_label) for case in dataset.cases]
    metrics = calculate_metrics(observations, prices or TokenPrices())
    return EvalReport(
        dataset_version=dataset.version,
        model=model,
        prompt_version=prompt_version,
        metrics=metrics,
        gates=evaluate_gates(metrics, thresholds or GateThresholds()),
    )
