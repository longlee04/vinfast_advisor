"""Acceptance contract for section 17 of the conversation refactor spec (Ngọc, dev/ngoc).

Đọc `eval/datasets/architecture_golden.json` — bộ riêng, kỳ vọng nguyên văn của
kiến trúc mới, không gate hành vi develop (hướng 1, 2026-08-28).
"""

from eval.conversation.loader import load_architecture_golden_dataset as load_conversation_dataset
from eval.conversation.models import GoldenCase

HEAVY_STAGES = {"policy_rag", "candidate_filter", "scoring", "tco"}


def _golden_scenarios():
    dataset = load_conversation_dataset()
    return [scenario for scenario in dataset.scenarios if scenario.golden_case is not None]


def test_all_fourteen_required_golden_conversations_are_unique_and_executable() -> None:
    scenarios = _golden_scenarios()

    assert len(scenarios) == len(GoldenCase) == 14
    assert {scenario.golden_case for scenario in scenarios} == set(GoldenCase)
    assert all("architecture_golden" in scenario.groups for scenario in scenarios)
    assert all(scenario.workflow is not None for scenario in scenarios)
    assert all(scenario.turns for scenario in scenarios)


def test_every_golden_workflow_declares_non_contradictory_stage_expectations() -> None:
    for scenario in _golden_scenarios():
        workflow = scenario.workflow
        assert workflow is not None
        assert workflow.required_stages
        assert not set(workflow.required_stages).intersection(workflow.forbidden_stages)


def test_casual_out_of_scope_and_test_drive_forbid_unnecessary_heavy_stages() -> None:
    cases = {
        GoldenCase.GREETING,
        GoldenCase.THANK_YOU,
        GoldenCase.OUT_OF_SCOPE,
        GoldenCase.TEST_DRIVE_BYPASS,
    }

    for scenario in _golden_scenarios():
        if scenario.golden_case not in cases:
            continue
        assert scenario.workflow is not None
        assert HEAVY_STAGES <= set(scenario.workflow.forbidden_stages)


def test_normal_policy_qa_requires_a_source_but_not_default_hitl() -> None:
    cases = {scenario.golden_case: scenario for scenario in _golden_scenarios()}

    for case in (GoldenCase.WARRANTY_QUESTION, GoldenCase.BATTERY_WARRANTY_COMPLAINT):
        workflow = cases[case].workflow
        assert workflow is not None
        assert workflow.terminal == "ANSWER"
        assert workflow.requires_authoritative_source is True
        assert "policy_rag" in workflow.required_stages
        assert "hitl" in workflow.forbidden_stages


def test_risky_cases_require_hitl_or_safe_handling() -> None:
    cases = {scenario.golden_case: scenario for scenario in _golden_scenarios()}

    for case in (
        GoldenCase.EXPLICIT_HUMAN_REQUEST,
        GoldenCase.SERIOUS_SAFETY_COMPLAINT,
        GoldenCase.INSUFFICIENT_POLICY_EVIDENCE,
        GoldenCase.REPEATED_VALIDATION_FAILURE,
    ):
        workflow = cases[case].workflow
        assert workflow is not None
        assert workflow.terminal in {"HITL", "SAFE_HANDLING"}
        assert "hitl" in workflow.required_stages


def test_budget_mutations_share_the_same_semantic_anchor() -> None:
    dataset = load_conversation_dataset()
    mutation_turns = [scenario.turns[0] for scenario in dataset.scenarios if "mutation_paraphrase" in scenario.groups]

    assert {turn.user_message for turn in mutation_turns} >= {
        "700 triệu",
        "700tr thôi",
        "tầm bảy trăm",
        "700 củ",
        "chắc 700 là căng",
    }
    assert {turn.expected_budget_anchor_vnd for turn in mutation_turns} == {700_000_000}
