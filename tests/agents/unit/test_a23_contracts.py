"""A2-3 contract tests for raw extraction and pending feature persistence."""

from __future__ import annotations

from typing import get_type_hints

from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.values import DialogueAct, ScopeLabel, TaskAction
from src.agents.ports import LLMPort, PendingFeatureMentionPort
from src.agents.prompts.slot_extraction_prompts import build_tool_schema


def test_llm_port_returns_raw_pydantic_payload() -> None:
    hints = get_type_hints(LLMPort.extract_slots)

    assert hints["return"] is LLMExtractionPayload


def test_pending_feature_port_uses_authenticated_atomic_consume() -> None:
    record_hints = get_type_hints(PendingFeatureMentionPort.record)
    consume_hints = get_type_hints(PendingFeatureMentionPort.consume)

    assert record_hints["customer_id"] is str
    assert consume_hints["customer_id"] is str
    assert consume_hints["return"] == list[str]


def test_agent_transaction_exposes_pending_feature_port() -> None:
    from src.agents.ports import AgentTransaction

    assert "pending_mentions" in get_type_hints(AgentTransaction)


def test_turn_understanding_schema_collects_all_routing_fields_in_one_call() -> None:
    schema = build_tool_schema(None, [])
    parameters = schema["parameters"]
    assert isinstance(parameters, dict)
    properties = parameters["properties"]

    assert set(parameters["required"]) == {
        "scope",
        "dialogue_act",
        "task_action",
        "intents",
    }
    assert set(properties["scope"]["enum"]) == {
        ScopeLabel.IN_SCOPE.value,
        ScopeLabel.SOCIAL.value,
        ScopeLabel.OUT_OF_SCOPE.value,
    }
    assert set(properties["dialogue_act"]["enum"]) == {member.value for member in DialogueAct}
    assert set(properties["task_action"]["enum"]) == {member.value for member in TaskAction}
