"""Coverage and schema checks for the golden conversation dataset."""

from eval.conversation.loader import load_conversation_dataset
from eval.conversation.models import Decision, SlotName


def test_dataset_has_broad_multi_turn_and_adversarial_coverage() -> None:
    dataset = load_conversation_dataset()
    groups = {group for scenario in dataset.scenarios for group in scenario.groups}
    multi_turn_scenarios = [scenario for scenario in dataset.scenarios if len(scenario.turns) > 1]

    assert len(dataset.scenarios) >= 40
    assert sum(len(scenario.turns) for scenario in dataset.scenarios) >= 50
    assert len(multi_turn_scenarios) >= 5
    assert {
        "ambiguity",
        "branch_isolation",
        "branch_switch",
        "completion",
        "correction",
        "lookup_interrupt",
        "multi_slot",
        "multi_turn",
        "negation",
        "no_false_fill",
        "seat_phrasing",
        "short_answer",
        "memory",
        "referent_resolution",
        "ab_reconciliation",
    } <= groups


def test_memory_eval_has_referent_isolation_and_ab_cases() -> None:
    dataset = load_conversation_dataset()
    memory = [scenario for scenario in dataset.scenarios if "memory" in scenario.groups]

    assert len(memory) >= 8
    assert any("session_isolation" in scenario.groups for scenario in memory)
    assert any("branch_switch" in scenario.groups for scenario in memory)
    assert sum("ab_reconciliation" in scenario.groups for scenario in memory) >= 2


def test_dataset_covers_both_vehicle_branches_and_unresolved_turns() -> None:
    dataset = load_conversation_dataset()
    expected_types = {
        turn.expected_slots.get(SlotName.VEHICLE_TYPE) for scenario in dataset.scenarios for turn in scenario.turns
    }

    assert "CAR" in expected_types
    assert "ELECTRIC_MOTORBIKE" in expected_types
    assert any(not turn.expected_slots for scenario in dataset.scenarios for turn in scenario.turns)
    assert any(scenario.expects_completion for scenario in dataset.scenarios)


def test_every_turn_declares_intent_and_graph_decision_expectations() -> None:
    dataset = load_conversation_dataset()

    for scenario in dataset.scenarios:
        for turn in scenario.turns:
            assert turn.expected_intents is not None
            assert turn.expected_decision is not None

    assert any(
        turn.expected_intents == [] and turn.expected_decision == Decision.CLARIFY_INTENT
        for scenario in dataset.scenarios
        for turn in scenario.turns
    )


def test_evidence_backed_scenarios_reference_the_evidence_catalog() -> None:
    dataset = load_conversation_dataset()
    evidence_scenarios = [scenario for scenario in dataset.scenarios if scenario.evidence_ids]

    assert evidence_scenarios
    assert {evidence for scenario in evidence_scenarios for evidence in scenario.evidence_ids} >= {
        "E01",
        "E02",
        "E03",
        "E04",
        "E05",
    }
