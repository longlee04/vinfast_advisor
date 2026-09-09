"""Todo 5 closed bottleneck detection contract and tool schema."""

from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    BottleneckDetectionStatus,
    BottleneckNone,
    BottleneckUnavailable,
)
from src.agents.domain.customer_profile import Bottleneck
from src.agents.prompts.bottleneck_detection import (
    BOTTLENECK_DETECTION_PROMPT_VERSION,
    build_bottleneck_detection_tool,
)


def test_prompt_version_increments_for_confidence_schema() -> None:
    assert BOTTLENECK_DETECTION_PROMPT_VERSION == "bottleneck-detection-v2"


def test_detection_contract_has_three_typed_results() -> None:
    # Given / When
    detected = BottleneckDetected(
        status=BottleneckDetectionStatus.DETECTED,
        label=Bottleneck.PRICE,
        evidence_quote="Giá cao, key=[REDACTED]",
    )
    none = BottleneckNone(status=BottleneckDetectionStatus.NONE)
    unavailable = BottleneckUnavailable(status=BottleneckDetectionStatus.UNAVAILABLE)

    # Then
    assert detected.label is Bottleneck.PRICE
    assert detected.evidence_quote == "Giá cao, key=[REDACTED]"
    assert detected.confidence == 0.0
    assert none.status is BottleneckDetectionStatus.NONE
    assert unavailable.status is BottleneckDetectionStatus.UNAVAILABLE


def test_tool_schema_closes_status_and_label_enums() -> None:
    # Given / When
    parameters = build_bottleneck_detection_tool()["function"]["parameters"]

    # Then
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["status"]["enum"] == ["DETECTED", "NONE"]
    assert parameters["properties"]["label"]["enum"] == [label.value for label in Bottleneck]
    assert parameters["properties"]["confidence"]["type"] == "number"


def test_customer_bottleneck_enum_excludes_unavailable() -> None:
    # Given / When
    labels = [label.value for label in Bottleneck]

    # Then
    assert labels == ["PRICE", "CHARGING", "BATTERY", "RANGE"]
    assert "UNAVAILABLE" not in labels
