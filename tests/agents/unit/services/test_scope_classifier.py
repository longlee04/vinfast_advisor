"""Application-service tests for A6-2 classification and audit logging."""

from uuid import UUID

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.values import ScopeLabel
from src.agents.prompts.scope_prompts import (
    CLASSIFIER_SCOPE_LABELS,
    SCOPE_CLASSIFIER_INSTRUCTIONS,
    build_scope_prompt,
)
from src.agents.services.scope_classifier import DefaultScopeClassifierService

SESSION_ID = UUID("10000000-0000-0000-0000-000000000101")


class FakeClassifier:
    def __init__(self, output: str) -> None:
        self.output = output
        self.prompts: list[str] = []

    async def classify_scope(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.output


class FakeSessionContext:
    def current_session_id(self) -> UUID:
        return SESSION_ID


class FakeScopeLog:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str, ScopeLabel, str | None]] = []

    async def log(
        self,
        *,
        session_id: UUID,
        utterance: str,
        classification: ScopeLabel,
        reason: str | None,
    ) -> None:
        self.calls.append((session_id, utterance, classification, reason))


@pytest.mark.asyncio
async def test_competitor_question_is_out_of_scope_logged_and_has_escape() -> None:
    classifier = FakeClassifier("OUT_OF_SCOPE")
    scope_log = FakeScopeLog()
    service = DefaultScopeClassifierService(
        classifier=classifier,
        session_context=FakeSessionContext(),
        scope_log=scope_log,
    )
    question = "So sánh VinFast với Tesla giúp tôi"

    decision = await service.classify_with_guidance(user_message=question, canonical=build_canonical_text(question))

    assert decision.label is ScopeLabel.OUT_OF_SCOPE
    assert decision.limitation
    assert decision.escape_route
    assert scope_log.calls == [(SESSION_ID, question, ScopeLabel.OUT_OF_SCOPE, decision.limitation)]
    assert question in classifier.prompts[0]
    assert all(label.value in classifier.prompts[0] for label in CLASSIFIER_SCOPE_LABELS)


@pytest.mark.asyncio
@pytest.mark.parametrize("label", list(ScopeLabel))
async def test_frozen_classify_contract_returns_label_and_logs_every_classification(
    label: ScopeLabel,
) -> None:
    scope_log = FakeScopeLog()
    service = DefaultScopeClassifierService(
        classifier=FakeClassifier(label.value),
        session_context=FakeSessionContext(),
        scope_log=scope_log,
    )

    result = await service.classify(user_message="câu hỏi", canonical=build_canonical_text("câu hỏi"))

    expected = ScopeLabel.IN_SCOPE if label is ScopeLabel.MISSING_DATA else label
    assert result is expected
    assert len(scope_log.calls) == 1
    assert scope_log.calls[0][2] is expected


@pytest.mark.asyncio
async def test_legacy_missing_data_is_deferred_to_intent_specific_handling() -> None:
    """Scope must not guess whether lookup/advisory fields are sufficient."""

    scope_log = FakeScopeLog()
    service = DefaultScopeClassifierService(
        classifier=FakeClassifier("MISSING_DATA"),
        session_context=FakeSessionContext(),
        scope_log=scope_log,
    )

    decision = await service.classify_with_guidance(
        user_message="tất cả các mẫu VF 8 hiện tại", canonical=build_canonical_text("tất cả các mẫu VF 8 hiện tại")
    )

    assert decision.label is ScopeLabel.IN_SCOPE
    assert decision.user_response == ""
    assert scope_log.calls[0][2] is ScopeLabel.IN_SCOPE
    assert "deferred" in (scope_log.calls[0][3] or "")


@pytest.mark.asyncio
async def test_invalid_classifier_label_is_rejected_without_audit_guess() -> None:
    scope_log = FakeScopeLog()
    service = DefaultScopeClassifierService(
        classifier=FakeClassifier("MAYBE"),
        session_context=FakeSessionContext(),
        scope_log=scope_log,
    )

    with pytest.raises(ValueError, match="scope label"):
        await service.classify(user_message="câu hỏi", canonical=build_canonical_text("câu hỏi"))

    assert scope_log.calls == []


@pytest.mark.asyncio
async def test_empty_message_is_rejected_before_classifier_call() -> None:
    classifier = FakeClassifier("IN_SCOPE")
    service = DefaultScopeClassifierService(
        classifier=classifier,
        session_context=FakeSessionContext(),
        scope_log=FakeScopeLog(),
    )

    with pytest.raises(ValueError, match="user_message"):
        await service.classify_with_guidance(user_message="  ", canonical=build_canonical_text("  "))

    assert classifier.prompts == []


def test_scope_prompt_allows_comparison_between_vinfast_models() -> None:
    assert "giữa các mẫu xe VinFast" in SCOPE_CLASSIFIER_INSTRUCTIONS
    assert "so sánh với xe hãng khác" in SCOPE_CLASSIFIER_INSTRUCTIONS
    assert "<utterance>VF 3 với VF 5 khác nhau chỗ nào</utterance>" in build_scope_prompt(
        "VF 3 với VF 5 khác nhau chỗ nào"
    )


def test_scope_prompt_does_not_ask_the_model_to_judge_missing_fields() -> None:
    prompt = build_scope_prompt("tất cả các mẫu VF 9")

    assert "MISSING_DATA" not in prompt
    assert "không tự quyết định phạm vi" in SCOPE_CLASSIFIER_INSTRUCTIONS
    assert "hành động hoặc mục đích" in SCOPE_CLASSIFIER_INSTRUCTIONS


@pytest.mark.asyncio
async def test_a_price_cut_request_is_not_treated_as_out_of_scope() -> None:
    """[A7-4] Câu mặc cả phải chảy tiếp tới cổng báo giá, không bị từ chối tại đây.

    Classifier LLM gắn OUT_OF_SCOPE cho "anh giảm cho em 20 triệu" vì agent không
    được tự quyết giá. Nhưng dừng lượt ở đây là từ chối đúng nhóm câu đáng lẽ
    phải tới tay tư vấn viên nhất — và lượt chết trước khi chạm `quote_gate`.
    """

    classifier = FakeClassifier("OUT_OF_SCOPE")
    scope_log = FakeScopeLog()
    service = DefaultScopeClassifierService(
        classifier=classifier,
        session_context=FakeSessionContext(),
        scope_log=scope_log,
    )
    question = "anh giảm cho em 20 triệu được không"

    decision = await service.classify_with_guidance(user_message=question, canonical=build_canonical_text(question))

    assert decision.label is ScopeLabel.IN_SCOPE
    assert decision.limitation is None  # không trả lời từ chối cho khách
    # Dòng audit A6-2 vẫn phải nói ra việc classifier đã nghĩ khác.
    [(_, _, logged_label, reason)] = scope_log.calls
    assert logged_label is ScopeLabel.IN_SCOPE
    assert reason is not None
    assert "OUT_OF_SCOPE" in reason and "is_negotiated" in reason


@pytest.mark.asyncio
async def test_a_genuinely_out_of_scope_question_is_still_rejected() -> None:
    """Override chỉ áp cho câu mang yếu tố báo giá, không nới phạm vi nói chung."""

    service = DefaultScopeClassifierService(
        classifier=FakeClassifier("OUT_OF_SCOPE"),
        session_context=FakeSessionContext(),
        scope_log=FakeScopeLog(),
    )

    decision = await service.classify_with_guidance(
        user_message="hôm nay Hà Nội mưa không", canonical=build_canonical_text("hôm nay Hà Nội mưa không")
    )

    assert decision.label is ScopeLabel.OUT_OF_SCOPE
