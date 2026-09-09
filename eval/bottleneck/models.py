"""Typed contracts for bottleneck classifier evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvalLabel(StrEnum):
    PRICE = "PRICE"
    CHARGING = "CHARGING"
    BATTERY = "BATTERY"
    RANGE = "RANGE"
    NONE = "NONE"


class DetectionStatus(StrEnum):
    DETECTED = "DETECTED"
    NONE = "NONE"
    UNAVAILABLE = "UNAVAILABLE"


class BottleneckCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    expected_label: EvalLabel
    eligible: bool
    anchor: str | None = None
    groups: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def anchor_requires_eligibility(self) -> BottleneckCase:
        if self.anchor is not None and not self.eligible:
            raise ValueError("anchor requires eligible context")
        return self


class BottleneckDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    cases: tuple[BottleneckCase, ...]


class EvalObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    expected_label: EvalLabel
    predicted_label: EvalLabel | None
    status: DetectionStatus
    latency_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    invalid_payload: bool


class TokenPrices(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_usd_per_million: float = Field(default=2.0, ge=0)
    output_usd_per_million: float = Field(default=8.0, ge=0)


class GateThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)

    macro_f1: float = 0.85
    price_precision: float = 0.90
    p95_latency_ms: int = 3_000


class LabelMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    precision: float
    recall: float
    f1: float
    support: int


class EvalMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_count: int
    per_label: dict[EvalLabel, LabelMetrics]
    macro_f1: float
    confusion: dict[EvalLabel, dict[EvalLabel, int]]
    status_counts: dict[DetectionStatus, int]
    p50_latency_ms: int
    p95_latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    invalid_payload_count: int


class GateFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    actual: float
    threshold: float


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    failures: tuple[GateFailure, ...]


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: int
    model: str
    prompt_version: str
    metrics: EvalMetrics
    gates: GateResult


class CaseDetector(Protocol):
    async def evaluate(self, case_id: str, text: str, expected: EvalLabel) -> EvalObservation: ...
