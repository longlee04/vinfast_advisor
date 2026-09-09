"""A6-2 scope classification, guidance and complete audit logging."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.agents.domain.budget_parsing import mentions_budget
from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.quote_risk import detect_risk_flags
from src.agents.domain.scope import ScopeDecision, decision_for
from src.agents.domain.values import ScopeLabel
from src.agents.prompts.scope_prompts import build_scope_prompt
from src.agents.services.intent_heuristics import is_direct_human_request


class ScopeClassificationPort(Protocol):
    """Narrow LLM classification capability returning one closed-set label."""

    async def classify_scope(self, *, prompt: str) -> str: ...


class ScopeSessionContext(Protocol):
    """Provide the session bound to the current asynchronous request context."""

    def current_session_id(self) -> UUID: ...


class ScopeLogPort(Protocol):
    """Persist every scope decision for later manual accuracy review."""

    async def log(
        self,
        *,
        session_id: UUID,
        utterance: str,
        classification: ScopeLabel,
        reason: str | None,
    ) -> None: ...


class DefaultScopeClassifierService:
    """Classify into three labels, log the result and provide safe rejection guidance."""

    def __init__(
        self,
        *,
        classifier: ScopeClassificationPort,
        session_context: ScopeSessionContext,
        scope_log: ScopeLogPort,
    ) -> None:
        self._classifier = classifier
        self._session_context = session_context
        self._scope_log = scope_log

    async def classify(self, *, user_message: str, canonical: CanonicalText) -> ScopeLabel:
        """Implement the frozen service contract and persist the classification."""

        return (await self.classify_with_guidance(user_message=user_message, canonical=canonical)).label

    async def classify_with_guidance(
        self,
        *,
        user_message: str,
        canonical: CanonicalText,
        conversation_context: str = "",
        advisory_context: bool = False,
    ) -> ScopeDecision:
        """Return the richer decision used by A4 to render rejection guidance."""

        if not user_message.strip():
            raise ValueError("user_message must not be empty")
        raw_label = await self._classifier.classify_scope(prompt=build_scope_prompt(user_message, conversation_context))
        return await self.decide_from_label(
            raw_label=raw_label,
            user_message=user_message,
            canonical=canonical,
            advisory_context=advisory_context,
        )

    async def decide_from_label(
        self,
        *,
        raw_label: ScopeLabel | str,
        user_message: str,
        canonical: CanonicalText,
        advisory_context: bool = False,
    ) -> ScopeDecision:
        """Audit a label already produced by the unified turn-understanding call."""

        if not user_message.strip():
            raise ValueError("user_message must not be empty")
        try:
            label = ScopeLabel(str(raw_label).strip())
        except ValueError as error:
            raise ValueError("classifier returned an invalid scope label") from error
        effective, reason = _defer_missing_data(label)
        effective, quote_reason = _apply_quote_risk_override(effective, user_message, canonical)
        reason = quote_reason or reason
        effective, budget_reason = _apply_budget_update_override(
            effective, user_message, advisory_context=advisory_context
        )
        reason = budget_reason or reason
        # Seed = danh tính phiên, để lời từ chối đổi cách nói giữa các hội thoại
        # (đo trên prod: lặp y nguyên 28 lần). Nó CHỈ đổi câu chữ — `effective` đã
        # quyết xong ở trên, seed không chạm tới một nhánh quyết định nào.
        decision = decision_for(
            label=effective,
            utterance=user_message,
            seed=str(self._session_context.current_session_id() or ""),
        )
        await self._scope_log.log(
            session_id=self._session_context.current_session_id(),
            utterance=user_message,
            classification=effective,
            # Ghi lý do override thay cho `limitation` (đằng nào cũng `None` khi
            # đã đổi sang IN_SCOPE) để dòng audit A6-2 không im lặng đánh mất
            # việc classifier đã nói khác.
            reason=reason or decision.limitation,
        )
        return decision


def _defer_missing_data(label: ScopeLabel) -> tuple[ScopeLabel, str | None]:
    """Move field sufficiency out of the domain-scope classifier.

    ``MISSING_DATA`` remains in the persisted enum for backward compatibility,
    but a probabilistic pre-router cannot know which fields a later intent needs.
    Intent routing, slot planning and data retrieval make that decision instead.
    """

    if label is not ScopeLabel.MISSING_DATA:
        return label, None
    return (
        ScopeLabel.IN_SCOPE,
        "Legacy MISSING_DATA deferred to intent-specific routing and retrieval.",
    )


def _apply_quote_risk_override(
    label: ScopeLabel, user_message: str, canonical: CanonicalText
) -> tuple[ScopeLabel, str | None]:
    """Câu mang yếu tố báo giá rủi ro KHÔNG bao giờ là "ngoài phạm vi" (A7-4).

    Khách xin giảm giá, hỏi ưu đãi, hay hỏi điều khoản trả góp đều là chuyện mua
    xe VinFast — thuộc phạm vi, chỉ là agent không được tự quyết. Trả lời "em chỉ
    hỗ trợ tư vấn từ dữ liệu đã xác minh" rồi dừng lượt là kết cục sai: nó từ
    chối đúng nhóm câu đáng lẽ phải tới tay tư vấn viên nhất, và lượt chết ngay
    tại `classify_scope` nên không bao giờ chạm tới `quote_gate`.

    Chỉ nâng nhãn lên IN_SCOPE, không tự trả lời gì: cổng rủi ro ở sau mới là nơi
    quyết định chặn hay không, và mặc định của nó là chặn.

    So khớp chạy trên `canonical` sinh tại chain — gate không tự normalize
    (ENG REVIEW AMENDMENT 2).
    """

    if label not in {ScopeLabel.MISSING_DATA, ScopeLabel.OUT_OF_SCOPE}:
        return label, None
    if is_direct_human_request(user_message, canonical):
        return ScopeLabel.IN_SCOPE, "A7-4 human handoff request override to IN_SCOPE."
    triggered = [
        name for name, value in detect_risk_flags(user_message=user_message, canonical=canonical).items() if value
    ]
    if not triggered:
        return label, None
    return ScopeLabel.IN_SCOPE, (
        f"A7-4 quote-risk override: classifier trả {label.value}, "
        f"chuyển IN_SCOPE để cổng báo giá xử lý ({', '.join(sorted(triggered))})."
    )


def _apply_budget_update_override(
    label: ScopeLabel, user_message: str, *, advisory_context: bool
) -> tuple[ScopeLabel, str | None]:
    """Sửa lại ngân sách GIỮA một cuộc tư vấn không bao giờ là "ngoài phạm vi".

    Bug đã quan sát: phiên đã chốt loại xe và một mức ngân sách, khách gõ tiếp
    "giá từ 400 -600 triệu" và nhận về câu từ chối "em chỉ hỗ trợ tư vấn từ dữ liệu
    đã được xác minh". Cùng câu đó thêm hai chữ "ô tô" ở đầu thì lại chạy bình
    thường — dấu hiệu kinh điển của một bộ phân loại xác suất chấm một mẩu câu
    đứng riêng, chứ không phải một luật nghiệp vụ.

    Guardrail A6-2 không sai: "giá từ 400 -600 triệu" đứng một mình đúng là không
    khớp tác vụ nào. Nó chỉ không biết câu đó đang nối vào cái gì. Ở đây thì biết,
    và biết một cách DETERMINISTIC: phiên đang giữa luồng tư vấn, và câu này đọc
    ra được một mức tiền cụ thể.

    Cùng khuôn với `_apply_quote_risk_override`: chỉ NÂNG nhãn lên IN_SCOPE, không
    tự trả lời gì. Router và slot planner phía sau vẫn quyết định lượt đi đâu.
    """

    if label is not ScopeLabel.OUT_OF_SCOPE or not advisory_context:
        return label, None
    if not mentions_budget(user_message):
        return label, None
    return ScopeLabel.IN_SCOPE, (
        "A7-10 budget-update override: classifier trả OUT_OF_SCOPE, chuyển IN_SCOPE "
        "vì phiên đang tư vấn dở và câu này nêu một mức ngân sách cụ thể."
    )
