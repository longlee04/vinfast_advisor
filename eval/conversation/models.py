"""Typed contracts for the multi-turn slot-conversation evaluation dataset."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SlotName(StrEnum):
    """Stable dataset vocabulary, intentionally independent from agent runtime."""

    VEHICLE_TYPE = "vehicle_type"
    PASSENGER_COUNT = "passenger_count"
    REQUIRED_RANGE_KM = "required_range_km"
    HOME_CHARGING = "home_charging"
    BUDGET_MAX_VND = "budget_max_vnd"
    BUDGET_MIN_VND = "budget_min_vnd"
    #: Con số khách nói ra khi câu là ước lượng ("khoảng 500 triệu") — xem
    #: `src/agents/domain/values.SlotName.BUDGET_STATED_VND`. Enum này cố ý tách
    #: khỏi runtime, nhưng runtime ghi slot nào thì bộ chạy dataset đọc slot đó,
    #: nên thiếu một thành viên là cả bộ eval vỡ với `not a valid SlotName`.
    BUDGET_STATED_VND = "budget_stated_vnd"
    PURPOSE = "purpose"
    PURPOSE_BUCKET = "purpose_bucket"
    MAX_LOAD_KG = "max_load_kg"
    HABIT_NEED_TAGS = "habit_need_tags"
    #: Tỉnh ĐĂNG KÝ xe — khác `user_location` (nơi khách đang đứng). Runtime bắt
    #: đầu ghi slot này từ chính lời khách ("anh ở hồ chí minh…"), nên nó phải có
    #: mặt ở đây, đúng lý do đã ghi cho `BUDGET_STATED_VND` ngay trên.
    REGISTRATION_PROVINCE = "registration_province"


class Decision(StrEnum):
    """Customer-visible graph decision evaluated independently from slot state."""

    ASK = "ASK"
    LOOKUP = "LOOKUP"
    BROWSE = "BROWSE"
    #: [COMPARE_VEHICLES] Đặt 2–3 mẫu khách nêu tên cạnh nhau. Tách khỏi `LOOKUP`
    #: vì khách nhận một thứ khác hẳn: một bảng chung, không phải n bảng nối nhau.
    COMPARE = "COMPARE"
    RETRIEVE = "RETRIEVE"
    HYBRID = "HYBRID"
    CLARIFY_INTENT = "CLARIFY_INTENT"
    POLICY = "POLICY"
    HANDOFF = "HANDOFF"


SlotValue = str | int | float | bool | list[str] | None


class GoldenCase(StrEnum):
    """14 lớp hành vi bắt buộc — đưa từ nhánh dev/ngoc (Ngọc, 2026-08-27)."""

    BUDGET_ONLY = "budget_only"
    FOLLOWUP_ELLIPSIS = "followup_ellipsis"
    BUDGET_CORRECTION = "budget_correction"
    COMPARE_VF7_VF8 = "compare_vf7_vf8"
    WARRANTY_QUESTION = "warranty_question"
    BATTERY_WARRANTY_COMPLAINT = "battery_warranty_complaint"
    GREETING = "greeting"
    THANK_YOU = "thank_you"
    OUT_OF_SCOPE = "out_of_scope"
    EXPLICIT_HUMAN_REQUEST = "explicit_human_request"
    SERIOUS_SAFETY_COMPLAINT = "serious_safety_complaint"
    INSUFFICIENT_POLICY_EVIDENCE = "insufficient_policy_evidence"
    REPEATED_VALIDATION_FAILURE = "repeated_validation_failure"
    TEST_DRIVE_BYPASS = "test_drive_bypass"


class WorkflowExpectation(BaseModel):
    """Hợp đồng điều phối quan sát được, gắn với một golden case."""

    model_config = ConfigDict(frozen=True)

    terminal: Literal["ANSWER", "ASK", "HITL", "SAFE_HANDLING"]
    required_stages: list[str] = Field(default_factory=list)
    forbidden_stages: list[str] = Field(default_factory=list)
    requires_authoritative_source: bool = False


class ExtractionPayload(BaseModel):
    """Serializable LLM fixture without importing the production contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vehicle_type: str | None = None
    budget_max_vnd: str | int | float | None = None
    required_range_km: int | None = None
    range_period: str | None = None
    home_charging: bool | None = None
    purpose: str | None = None
    purpose_bucket: str | None = None
    passenger_count: int | None = None
    max_load_kg: int | None = None
    habit_need_tags: list[str] = Field(default_factory=list)
    feature_mentions: list[str] = Field(default_factory=list)
    vehicle_name_mentions: list[str] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=list)
    # Field của "kiến trúc mới" (dev/ngoc) — runner develop không dùng, chỉ nhận để dataset chung nạp được.
    task: str | None = None
    topics: list[str] = Field(default_factory=list)
    scope: str | None = None
    # Default khớp `LLMExtractionPayload` của src để test "soi gương" model_dump() vẫn đi thẳng.
    dialogue_act: str = "UNKNOWN"
    severity: str | None = None
    human_requested: bool = False
    variant_mentions: list[str] = Field(default_factory=list)
    constraint_updates: dict[str, SlotValue] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    """One customer message and its expected state after extraction."""

    model_config = ConfigDict(frozen=True)

    user_message: str = Field(min_length=1)
    llm_payload: ExtractionPayload = Field(default_factory=ExtractionPayload)
    expected_slots: dict[SlotName, SlotValue]
    forbidden_slots: list[SlotName] = Field(default_factory=list)
    provided_slots: list[SlotName] = Field(default_factory=list)
    expected_next_slot: SlotName | None = None
    expected_next_group: list[SlotName] | None = None
    expected_question: str | None = None
    correction_slots: list[SlotName] = Field(default_factory=list)
    expected_intents: list[str] | None = None
    forbidden_intents: list[str] = Field(default_factory=list)
    expected_decision: Decision | None = None
    memory_summary: str | None = None
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    expected_vehicle_mentions: list[str] = Field(default_factory=list)
    expected_task: str | None = None
    expected_topics: list[str] | None = None
    expected_scope: str | None = None
    expected_dialogue_act: str | None = None
    expected_severity: str | None = None
    expected_human_requested: bool | None = None
    expected_budget_anchor_vnd: int | None = None

    @model_validator(mode="before")
    @classmethod
    def fill_intent_and_decision_expectations(cls, value: object) -> object:
        """Keep the original dataset valid while making expectations explicit in memory."""

        if not isinstance(value, dict):
            return value
        data = dict(value)
        payload = data.get("llm_payload") or {}
        if "expected_vehicle_mentions" not in data:
            data["expected_vehicle_mentions"] = list(payload.get("vehicle_name_mentions") or [])
        if data.get("expected_intents") is None:
            data["expected_intents"] = list(payload.get("intents") or [])
        if data.get("expected_decision") is None:
            intents = set(data["expected_intents"])
            if "COMPARE_VEHICLES" in intents:
                decision = Decision.COMPARE
            elif {"ADVISORY", "CATALOG_LOOKUP"} <= intents:
                decision = Decision.HYBRID
            elif "CATALOG_BROWSE" in intents:
                decision = Decision.BROWSE
            elif "CATALOG_LOOKUP" in intents:
                decision = Decision.LOOKUP
            elif "ADVISORY" in intents:
                decision = Decision.ASK if data.get("expected_next_slot") is not None else Decision.RETRIEVE
            else:
                decision = Decision.CLARIFY_INTENT
            data["expected_decision"] = decision
        return data

    @model_validator(mode="after")
    def validate_expectations(self) -> ConversationTurn:
        """Reject contradictory golden expectations early."""

        overlap = set(self.expected_slots) & set(self.forbidden_slots)
        if overlap:
            names = ", ".join(sorted(slot.value for slot in overlap))
            raise ValueError(f"slot vừa expected vừa forbidden: {names}")
        missing_corrections = set(self.correction_slots) - set(self.expected_slots)
        if missing_corrections:
            names = ", ".join(sorted(slot.value for slot in missing_corrections))
            raise ValueError(f"correction slot thiếu golden value: {names}")
        return self


class ConversationScenario(BaseModel):
    """A durable conversation session containing one or more customer turns."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^SC\d{3}$")
    description: str = Field(min_length=1)
    groups: list[str] = Field(min_length=1)
    initial_slots: dict[SlotName, SlotValue] = Field(default_factory=dict)
    expects_completion: bool = False
    turns: list[ConversationTurn] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    golden_case: GoldenCase | None = None
    workflow: WorkflowExpectation | None = None


class ConversationDataset(BaseModel):
    """Versioned collection of conversation scenarios."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(ge=1)
    scenarios: list[ConversationScenario] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> ConversationDataset:
        """Scenario IDs are stable report keys and therefore must be unique."""

        identifiers = [scenario.id for scenario in self.scenarios]
        duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
        if duplicates:
            raise ValueError(f"scenario id trùng: {', '.join(duplicates)}")
        return self


class TurnEvaluation(BaseModel):
    """Observed and expected state for one evaluated turn."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    turn_number: int = Field(ge=1)
    groups: list[str]
    actual_slots: dict[SlotName, SlotValue]
    expected_slots: dict[SlotName, SlotValue]
    forbidden_present: list[SlotName]
    actual_next_slot: SlotName | None
    expected_next_slot: SlotName | None
    actual_next_group: list[SlotName] = Field(default_factory=list)
    expected_next_group: list[SlotName] | None = None
    actual_question: str | None = None
    expected_question: str | None = None
    provided_slots: list[SlotName]
    correction_slots: list[SlotName]
    raw_intents: list[str] = Field(default_factory=list)
    actual_intents: list[str]
    expected_intents: list[str]
    forbidden_intents: list[str]
    actual_decision: Decision
    raw_decision: Decision
    expected_decision: Decision
    actual_vehicle_mentions: list[str] = Field(default_factory=list)
    expected_vehicle_mentions: list[str] = Field(default_factory=list)
    memory_context_used: bool = False

    @property
    def correct_slot_count(self) -> int:
        """Number of golden slot/value pairs present exactly."""

        return sum(1 for slot, expected in self.expected_slots.items() if self.actual_slots.get(slot) == expected)

    @property
    def false_fill_count(self) -> int:
        """Actual slots absent from or different to the golden state."""

        return sum(1 for slot, actual in self.actual_slots.items() if self.expected_slots.get(slot) != actual)

    @property
    def missed_slot_count(self) -> int:
        """Golden slots missing or carrying the wrong value."""

        return len(self.expected_slots) - self.correct_slot_count

    @property
    def next_question_correct(self) -> bool:
        return self.actual_next_slot is self.expected_next_slot

    @property
    def next_group_correct(self) -> bool:
        """Khi golden chỉ định nhóm (T8) thì nhóm thực tế phải khớp y hệt."""
        if self.expected_next_group is None:
            return True
        return set(self.actual_next_group) == set(self.expected_next_group)

    @property
    def question_correct(self) -> bool:
        if self.expected_question is None:
            return True
        return self.actual_question == self.expected_question

    @property
    def redundant_question(self) -> bool:
        """Whether the engine asks for information supplied in this turn."""

        return self.actual_next_slot is not None and self.actual_next_slot in self.provided_slots

    @property
    def correction_count(self) -> int:
        return len(self.correction_slots)

    @property
    def correct_correction_count(self) -> int:
        return sum(1 for slot in self.correction_slots if self.actual_slots.get(slot) == self.expected_slots.get(slot))

    @property
    def passed(self) -> bool:
        return (
            self.actual_slots == self.expected_slots
            and not self.forbidden_present
            and self.next_question_correct
            and self.next_group_correct
            and self.question_correct
            and not self.redundant_question
            and set(self.actual_intents) == set(self.expected_intents)
            and not set(self.actual_intents).intersection(self.forbidden_intents)
            and self.actual_decision is self.expected_decision
            and set(self.actual_vehicle_mentions) == set(self.expected_vehicle_mentions)
        )


class ScenarioEvaluation(BaseModel):
    """All evaluated turns and completion state for one scenario."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    description: str
    groups: list[str]
    expects_completion: bool
    turns: list[TurnEvaluation]
    completed_at_turn: int | None = None

    @property
    def passed(self) -> bool:
        completion_ok = not self.expects_completion or self.completed_at_turn is not None
        return completion_ok and all(turn.passed for turn in self.turns)


class ConversationRun(BaseModel):
    """Complete result of one dataset execution."""

    model_config = ConfigDict(frozen=True)

    scenarios: list[ScenarioEvaluation]

    @property
    def turns(self) -> list[TurnEvaluation]:
        return [turn for scenario in self.scenarios for turn in scenario.turns]


class MetricReport(BaseModel):
    """Aggregate quality indicators for one conversation evaluation run."""

    model_config = ConfigDict(frozen=True)

    scenario_count: int
    turn_count: int
    slot_precision: float | None
    slot_recall: float | None
    false_fill_rate: float | None
    redundant_question_rate: float | None
    next_question_accuracy: float | None
    correction_accuracy: float | None
    completion_rate: float | None
    average_turns_to_completion: float | None
    scenario_pass_rate: float | None
    group_pass_rates: dict[str, float | None]
    raw_intent_exact_match: float | None
    intent_exact_match: float | None
    intent_false_negative_rate: float | None
    intent_false_positive_rate: float | None
    decision_accuracy: float | None
    raw_decision_accuracy: float | None
    referent_resolution_accuracy: float | None
    false_memory_carry_over_rate: float | None
    context_carry_over_accuracy: float | None


def normalized_slots(slots: Mapping[SlotName, SlotValue]) -> dict[SlotName, SlotValue]:
    """Return a regular dict for stable Pydantic serialization and comparisons."""

    return dict(slots)
