"""Unit tests for the evidence-bound grounded reaction policy.

The policy must bind a complaint to the latest eligible assistant turn and
structured evidence. A deterministic acknowledgment can never invent facts:
when evidence is absent, stale, or from another session, the reaction is a
neutral acknowledgment that references nothing.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.reaction_policy import (
    NEUTRAL_ACK,
    ReactionContext,
    ReactionDecision,
    ReactionEvidence,
    complaint_topic,
    decide_reaction,
    is_eligible_evidence,
)
from src.agents.domain.values import DialogueAct, Topic

_MODEL_PATTERN = re.compile(r"\bVF\s*-?\s*(E?\d+)\b", re.IGNORECASE)
_PRICE_PATTERN = re.compile(r"\d")


def _assert_no_fabricated_facts(text: str) -> None:
    """A deterministic acknowledgment must not invent a model or a price."""

    assert _MODEL_PATTERN.search(text) is None, text
    assert _PRICE_PATTERN.search(text) is None, text


def _price_evidence(
    *,
    conversation_id: object,
    message_id: object,
    vehicle_model: str | None = "VF 8",
) -> ReactionEvidence:
    return ReactionEvidence(
        conversation_id=conversation_id,
        message_id=message_id,
        topic=Topic.PRICE_TCO,
        answer="VF 8 có giá 1.2 tỷ đồng, phù hợp ngân sách của Quý khách.",
        vehicle_model=vehicle_model,
    )


def test_complaint_only_with_eligible_evidence_grounds_and_skips_reretrieval() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=message_id)
    context = ReactionContext(
        conversation_id=conversation_id,
        last_message_id=message_id,
        last_message_role="ASSISTANT",
    )

    result = decide_reaction(
        user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=evidence,
        context=context,
    )

    assert result.decision is ReactionDecision.GROUNDED_ACK
    assert result.no_reretrieval is True
    assert "VF 8" in result.text


def test_blank_session_returns_neutral_ack() -> None:
    context = ReactionContext(conversation_id=uuid4())

    result = decide_reaction(
        user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=None,
        context=context,
    )

    assert result.decision is ReactionDecision.IGNORE
    assert result.text.startswith(NEUTRAL_ACK)
    assert result.no_reretrieval is False


def test_mixed_complaint_and_question_acknowledges_then_continues() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=message_id)
    context = ReactionContext(
        conversation_id=conversation_id,
        last_message_id=message_id,
        last_message_role="ASSISTANT",
    )

    result = decide_reaction(
        user_message="Đắt quá, có mẫu nào rẻ hơn không?", canonical=build_canonical_text("Đắt quá, có mẫu nào rẻ hơn không?"),
        dialogue_acts={DialogueAct.COMPLAIN, DialogueAct.REQUEST},
        evidence=evidence,
        context=context,
    )

    assert result.decision is ReactionDecision.MIXED_PREFIX
    assert result.no_reretrieval is False
    assert result.text


def test_stale_evidence_message_id_mismatch_returns_neutral() -> None:
    conversation_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=uuid4())
    context = ReactionContext(
        conversation_id=conversation_id,
        last_message_id=uuid4(),
        last_message_role="ASSISTANT",
    )

    result = decide_reaction(
        user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=evidence,
        context=context,
    )

    assert result.decision is ReactionDecision.IGNORE
    assert result.text.startswith(NEUTRAL_ACK)


def test_cross_session_evidence_returns_neutral() -> None:
    evidence = _price_evidence(conversation_id=uuid4(), message_id=uuid4())
    context = ReactionContext(
        conversation_id=uuid4(),
        last_message_id=evidence.message_id,
        last_message_role="ASSISTANT",
    )

    result = decide_reaction(
        user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=evidence,
        context=context,
    )

    assert result.decision is ReactionDecision.IGNORE
    assert result.text.startswith(NEUTRAL_ACK)


def test_absent_evidence_returns_neutral() -> None:
    context = ReactionContext(
        conversation_id=uuid4(),
        last_message_id=uuid4(),
        last_message_role="ASSISTANT",
    )

    result = decide_reaction(
        user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=None,
        context=context,
    )

    assert result.decision is ReactionDecision.IGNORE
    assert result.text.startswith(NEUTRAL_ACK)


def test_last_message_not_assistant_breaks_adjacency() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=message_id)
    context = ReactionContext(
        conversation_id=conversation_id,
        last_message_id=message_id,
        last_message_role="USER",
    )

    result = decide_reaction(
        user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=evidence,
        context=context,
    )

    assert result.decision is ReactionDecision.IGNORE
    assert result.text.startswith(NEUTRAL_ACK)


def test_no_complaint_act_ignores_even_with_eligible_evidence() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=message_id)
    context = ReactionContext(
        conversation_id=conversation_id,
        last_message_id=message_id,
        last_message_role="ASSISTANT",
    )

    result = decide_reaction(
        user_message="VF 8 giá bao nhiêu?", canonical=build_canonical_text("VF 8 giá bao nhiêu?"),
        dialogue_acts={DialogueAct.REQUEST},
        evidence=evidence,
        context=context,
    )

    assert result.decision is ReactionDecision.IGNORE
    assert result.text.startswith(NEUTRAL_ACK)


def test_neutral_reactions_never_fabricate_model_or_price() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=message_id)
    scenarios = [
        (None, ReactionContext(conversation_id=uuid4())),
        (
            evidence,
            ReactionContext(
                conversation_id=conversation_id,
                last_message_id=uuid4(),
                last_message_role="ASSISTANT",
            ),
        ),
        (
            evidence,
            ReactionContext(
                conversation_id=uuid4(),
                last_message_id=message_id,
                last_message_role="ASSISTANT",
            ),
        ),
        (
            None,
            ReactionContext(
                conversation_id=conversation_id,
                last_message_id=message_id,
                last_message_role="ASSISTANT",
            ),
        ),
        (
            evidence,
            ReactionContext(
                conversation_id=conversation_id,
                last_message_id=message_id,
                last_message_role="USER",
            ),
        ),
    ]

    for scenario_evidence, scenario_context in scenarios:
        result = decide_reaction(
            user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
            dialogue_acts={DialogueAct.COMPLAIN},
            evidence=scenario_evidence,
            context=scenario_context,
        )
        assert result.decision is ReactionDecision.IGNORE
        assert result.text.startswith(NEUTRAL_ACK)
        _assert_no_fabricated_facts(result.text)


def test_grounded_text_without_model_never_mentions_model_or_price() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(
        conversation_id=conversation_id,
        message_id=message_id,
        vehicle_model=None,
    )
    context = ReactionContext(
        conversation_id=conversation_id,
        last_message_id=message_id,
        last_message_role="ASSISTANT",
    )

    result = decide_reaction(
        user_message="Đắt quá", canonical=build_canonical_text("Đắt quá"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=evidence,
        context=context,
    )

    assert result.decision is ReactionDecision.GROUNDED_ACK
    _assert_no_fabricated_facts(result.text)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Đắt quá", Topic.PRICE_TCO),
        ("Giá cao quá", Topic.PRICE_TCO),
        ("Vượt ngân sách của em", Topic.PRICE_TCO),
        ("Bảo hành ít quá", Topic.POLICY),
        ("Thời hạn bảo hành ngắn", Topic.POLICY),
        ("Tầm hoạt động thấp", Topic.CUSTOMER_EXPERIENCE),
        ("Quãng đường ngắn quá", Topic.CUSTOMER_EXPERIENCE),
    ],
)
def test_complaint_topic_detected_from_markers(message: str, expected: Topic) -> None:
    assert complaint_topic(message, None, build_canonical_text(message)) is expected


def test_complaint_topic_falls_back_to_evidence_topic_without_markers() -> None:
    evidence = _price_evidence(conversation_id=uuid4(), message_id=uuid4())

    assert complaint_topic("Em thấy không ổn", evidence, build_canonical_text("Em thấy không ổn")) is Topic.PRICE_TCO


def test_complaint_topic_returns_none_without_markers_or_evidence() -> None:
    assert complaint_topic("Em thấy không ổn", None, build_canonical_text("Em thấy không ổn")) is None


def test_eligibility_requires_present_same_session_and_assistant_adjacency() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=message_id)
    eligible = ReactionContext(
        conversation_id=conversation_id,
        last_message_id=message_id,
        last_message_role="ASSISTANT",
    )

    assert is_eligible_evidence(evidence=evidence, context=eligible) is True
    assert is_eligible_evidence(evidence=None, context=eligible) is False
    assert (
        is_eligible_evidence(
            evidence=evidence,
            context=ReactionContext(
                conversation_id=uuid4(),
                last_message_id=message_id,
                last_message_role="ASSISTANT",
            ),
        )
        is False
    )
    assert (
        is_eligible_evidence(
            evidence=evidence,
            context=ReactionContext(
                conversation_id=conversation_id,
                last_message_id=uuid4(),
                last_message_role="ASSISTANT",
            ),
        )
        is False
    )
    assert (
        is_eligible_evidence(
            evidence=evidence,
            context=ReactionContext(
                conversation_id=conversation_id,
                last_message_id=message_id,
                last_message_role="USER",
            ),
        )
        is False
    )


def test_price_complaint_asks_for_a_budget_instead_of_ending_the_turn() -> None:
    """Lượt chê giá phải MỞ ĐƯỜNG, không được dừng ở lời xác nhận.

    Đo trên prod 2026-08-26: "giá hơi cao" xuất hiện 5 lần ở 5 phiên, lần nào
    cũng trả đúng bốn chữ "Dạ, em hiểu ạ." rồi hết — ngõ cụt ngay tại lượt khách
    còn muốn mua nhất. Câu hỏi nối vào phải nhắm đúng `budget_max_vnd` vì đó là
    slot luồng đề xuất đã có sẵn đường xử lý.
    """

    result = decide_reaction(
        user_message="giá hơi cao",
        canonical=build_canonical_text("giá hơi cao"),
        dialogue_acts={DialogueAct.COMPLAIN},
        evidence=None,
        context=ReactionContext(conversation_id=uuid4()),
    )

    assert result.text.startswith(NEUTRAL_ACK)
    assert "ngân sách" in result.text
    assert result.text.rstrip().endswith("?")


def test_mixed_complaint_does_not_append_a_second_question() -> None:
    """Lượt vừa phàn nàn vừa hỏi: nhiệm vụ chính đã tự có câu hỏi của nó."""

    conversation_id = uuid4()
    message_id = uuid4()
    evidence = _price_evidence(conversation_id=conversation_id, message_id=message_id)

    result = decide_reaction(
        user_message="Đắt quá, còn mẫu nào rẻ hơn không?",
        canonical=build_canonical_text("Đắt quá, còn mẫu nào rẻ hơn không?"),
        dialogue_acts={DialogueAct.COMPLAIN, DialogueAct.REQUEST},
        evidence=evidence,
        context=ReactionContext(
            conversation_id=conversation_id,
            last_message_id=message_id,
            last_message_role="ASSISTANT",
        ),
    )

    assert result.decision is ReactionDecision.MIXED_PREFIX
    assert "ngân sách" not in result.text
