"""Typed contracts for the four-axis turn-understanding evaluation dataset.

Bốn trục lấy trực tiếp từ domain (`src.agents.domain.values`) — không đẻ bảng
phân loại song song thứ hai, vì `turn_axes.py` đã cảnh báo hai bảng song song là
mầm bug. Dataset chỉ thêm lớp kỳ vọng (golden) và cờ `expect_failure` cho ca
đầu ra hỏng.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.agents.domain.values import DialogueAct, IntentType, Severity, Topic


class TurnAxesPayload(BaseModel):
    """Serializable LLM fixture for four-axis extraction.

    Giữ kiểu `str` lỏng (không phải enum) để dataset có thể chứa ca đầu ra hỏng
    — sự nghiêm khắc nằm ở `LLMExtractionPayload` của production, nơi giá trị
    rác sẽ bị từ chối và runner ghi thành failed case.
    """

    # `extra="allow"`: fixture "hỏng" (TA008) cần mang một field mà payload production
    # từ chối về KIỂU (`passenger_count: "nhiều"`), vì nhãn enum lạ nay được bỏ chứ không
    # còn làm vứt payload (2026-08-29).
    model_config = ConfigDict(frozen=True, extra="allow")

    dialogue_act: str = "UNKNOWN"
    task: str | None = None
    primary_topic: str | None = None
    secondary_topics: list[str] = Field(default_factory=list)
    severity: str | None = None
    human_requested: bool = False
    intents: list[str] = Field(default_factory=list)
    vehicle_name_mentions: list[str] = Field(default_factory=list)


class TurnAxesExpectation(BaseModel):
    """Golden per-axis values for one turn, plus the expected failure contract."""

    model_config = ConfigDict(frozen=True)

    dialogue_act: DialogueAct
    task: IntentType | None = None
    primary_topic: Topic
    secondary_topics: tuple[Topic, ...] = ()
    severity: Severity = Severity.NORMAL
    human_requested: bool = False
    #: Ca đầu ra hỏng: runner PHẢI ghi failure_reason khớp giá trị này thì lượt
    #: mới tính là pass. `None` nghĩa là lượt phải chạy sạch và khớp mọi trục.
    expect_failure: str | None = None


class TurnAxesTurn(BaseModel):
    """One customer message and its expected four-axis state."""

    model_config = ConfigDict(frozen=True)

    user_message: str = Field(min_length=1)
    llm_payload: TurnAxesPayload = Field(default_factory=TurnAxesPayload)
    expected: TurnAxesExpectation


class TurnAxesScenario(BaseModel):
    """A single-turn four-axis evaluation case."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^TA\d{3}$")
    description: str = Field(min_length=1)
    groups: list[str] = Field(min_length=1)
    turns: list[TurnAxesTurn] = Field(min_length=1)


class TurnAxesDataset(BaseModel):
    """Versioned collection of four-axis scenarios."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(ge=1)
    scenarios: list[TurnAxesScenario] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> TurnAxesDataset:
        """Scenario IDs are stable report keys and therefore must be unique."""

        identifiers = [scenario.id for scenario in self.scenarios]
        duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
        if duplicates:
            raise ValueError(f"scenario id trùng: {', '.join(duplicates)}")
        return self


class TurnAxesResult(BaseModel):
    """Observed four-axis state after production normalization."""

    model_config = ConfigDict(frozen=True)

    dialogue_act: DialogueAct
    task: IntentType | None
    primary_topic: Topic
    secondary_topics: tuple[Topic, ...]
    severity: Severity
    human_requested: bool


class TurnAxesEvaluation(BaseModel):
    """Observed and expected four-axis state for one evaluated turn."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    turn_number: int = Field(ge=1)
    user_message: str
    actual: TurnAxesResult | None
    expected: TurnAxesExpectation
    failure_reason: str | None = None

    @property
    def failed(self) -> bool:
        """Whether the provider produced no usable output for this turn."""

        return self.failure_reason is not None

    @property
    def dialogue_act_match(self) -> bool:
        return self.actual is not None and self.actual.dialogue_act is self.expected.dialogue_act

    @property
    def task_match(self) -> bool:
        return self.actual is not None and self.actual.task is self.expected.task

    @property
    def primary_topic_match(self) -> bool:
        return self.actual is not None and self.actual.primary_topic is self.expected.primary_topic

    @property
    def secondary_topics_match(self) -> bool:
        """So sánh theo tập hợp: sai thành viên hoặc sai số lượng đều là trượt."""

        return self.actual is not None and set(self.actual.secondary_topics) == set(self.expected.secondary_topics)

    @property
    def severity_match(self) -> bool:
        return self.actual is not None and self.actual.severity is self.expected.severity

    @property
    def human_requested_match(self) -> bool:
        return self.actual is not None and self.actual.human_requested is self.expected.human_requested

    @property
    def joint_match(self) -> bool:
        """All six axes match exactly."""

        return (
            self.dialogue_act_match
            and self.task_match
            and self.primary_topic_match
            and self.secondary_topics_match
            and self.severity_match
            and self.human_requested_match
        )

    @property
    def passed(self) -> bool:
        """Ca kỳ vọng lỗi pass khi lỗi được ghi đúng; ca thường pass khi khớp mọi trục."""

        if self.expected.expect_failure is not None:
            return self.failure_reason == self.expected.expect_failure
        return not self.failed and self.joint_match


class TurnAxesScenarioEvaluation(BaseModel):
    """All evaluated turns for one scenario."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    description: str
    groups: list[str]
    turns: list[TurnAxesEvaluation]

    @property
    def passed(self) -> bool:
        return all(turn.passed for turn in self.turns)


class TurnAxesRun(BaseModel):
    """Complete result of one dataset execution."""

    model_config = ConfigDict(frozen=True)

    scenarios: list[TurnAxesScenarioEvaluation]

    @property
    def turns(self) -> list[TurnAxesEvaluation]:
        return [turn for scenario in self.scenarios for turn in scenario.turns]


class TurnAxesMetricReport(BaseModel):
    """Aggregate per-axis and joint quality indicators for one evaluation run."""

    model_config = ConfigDict(frozen=True)

    scenario_count: int
    turn_count: int
    dialogue_act_accuracy: float | None
    task_accuracy: float | None
    primary_topic_accuracy: float | None
    secondary_topics_accuracy: float | None
    severity_accuracy: float | None
    human_requested_accuracy: float | None
    joint_match_rate: float | None
    failure_rate: float | None
    scenario_pass_rate: float | None
    group_pass_rates: dict[str, float | None]
