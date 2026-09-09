"""Pure A6-2 scope decisions and mandatory rejection guidance."""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.domain.values import ScopeLabel
from src.agents.prompts.reply_variants import foreign_domain_parts


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """A classification plus safe user guidance when the request is rejected."""

    label: ScopeLabel
    utterance: str
    limitation: str | None
    escape_route: str | None

    def __post_init__(self) -> None:
        rejected = self.label in {ScopeLabel.MISSING_DATA, ScopeLabel.OUT_OF_SCOPE}
        if rejected and (not self.limitation or not self.escape_route):
            raise ValueError("rejected scope decision requires an escape route")
        if not rejected and (self.limitation is not None or self.escape_route is not None):
            raise ValueError("in-scope decision must not contain rejection guidance")

    @property
    def user_response(self) -> str:
        """Render the limitation and escape as one complete customer-facing response."""

        if self.limitation is None or self.escape_route is None:
            return ""
        return f"{self.limitation} {self.escape_route}"


def decision_for(*, label: ScopeLabel, utterance: str, seed: str = "") -> ScopeDecision:
    """Attach deterministic, non-empty guidance to every rejected classification.

    `seed` là danh tính phiên. Nó CHỈ đổi cách nói, không đổi một quyết định nào —
    `label` vẫn do tầng trên định. Mặc định rỗng để chỗ gọi cũ giữ nguyên hành vi.
    """

    if not utterance.strip():
        raise ValueError("scope decision requires a non-empty utterance")
    if label is ScopeLabel.MISSING_DATA:
        return ScopeDecision(
            label=label,
            utterance=utterance,
            limitation="Em chưa có đủ dữ liệu đã được xác minh để trả lời chính xác câu này.",
            escape_route=(
                "Anh/chị có thể nêu rõ mẫu xe VinFast cần hỏi, hoặc em sẽ chuyển câu hỏi cho tư vấn viên hỗ trợ."
            ),
        )
    if label is ScopeLabel.OUT_OF_SCOPE:
        return ScopeDecision(
            label=label,
            utterance=utterance,
            limitation=foreign_domain_parts(seed)[0],
            escape_route=foreign_domain_parts(seed)[1],
        )
    return ScopeDecision(
        label=label,
        utterance=utterance,
        limitation=None,
        escape_route=None,
    )
