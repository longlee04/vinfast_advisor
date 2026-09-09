"""Cập nhật ngân sách giữa một cuộc tư vấn không được coi là ngoài phạm vi."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.values import ScopeLabel
from src.agents.services.scope_classifier import DefaultScopeClassifierService

SESSION = UUID("cc000000-0000-0000-0000-000000000001")


class RejectingClassifier:
    """LLM phạm vi trả OUT_OF_SCOPE — đúng điểm yếu đã quan sát trên hội thoại thật."""

    async def classify_scope(self, *, prompt: str) -> str:
        return ScopeLabel.OUT_OF_SCOPE.value


class Context:
    def current_session_id(self) -> UUID:
        return SESSION


class Log:
    def __init__(self) -> None:
        self.rows: list[tuple[ScopeLabel, str | None]] = []

    async def log(self, *, session_id, utterance, classification, reason) -> None:
        self.rows.append((classification, reason))


def _service() -> tuple[DefaultScopeClassifierService, Log]:
    log = Log()
    return (
        DefaultScopeClassifierService(classifier=RejectingClassifier(), session_context=Context(), scope_log=log),
        log,
    )


@pytest.mark.parametrize(
    "message",
    ["giá từ 400 -600 triệu", "giá từ 400 - 600 triệu", "tầm 700 triệu", "dưới 500 triệu"],
)
@pytest.mark.asyncio
async def test_a_budget_update_mid_advisory_survives_the_scope_guardrail(
    message: str,
) -> None:
    service, log = _service()

    decision = await service.classify_with_guidance(
        user_message=message, canonical=build_canonical_text(message), advisory_context=True
    )

    assert decision.label is ScopeLabel.IN_SCOPE
    # Việc classifier đã nói khác vẫn phải để lại dấu trong audit A6-2.
    assert "budget-update override" in (log.rows[0][1] or "")


@pytest.mark.asyncio
async def test_the_same_sentence_is_still_rejected_outside_an_advisory_session() -> None:
    """Override đọc NGỮ CẢNH phiên, không nới lỏng guardrail cho mọi lượt."""

    service, _ = _service()

    decision = await service.classify_with_guidance(
        user_message="giá từ 400 -600 triệu",
        canonical=build_canonical_text("giá từ 400 -600 triệu"),
        advisory_context=False,
    )

    assert decision.label is ScopeLabel.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "message",
    ["mai Hà Nội có mưa không", "nhà em 4 người", "tư vấn cổ phiếu giúp tôi"],
)
@pytest.mark.asyncio
async def test_a_sentence_without_a_real_amount_is_not_rescued(message: str) -> None:
    """Override đòi một mức TIỀN cụ thể; không thì mọi con số đều lọt guardrail."""

    service, _ = _service()

    decision = await service.classify_with_guidance(
        user_message=message, canonical=build_canonical_text(message), advisory_context=True
    )

    assert decision.label is ScopeLabel.OUT_OF_SCOPE
