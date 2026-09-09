"""Exhaustive rejection-guidance tests for the A6-2 scope domain."""

import pytest

from src.agents.domain.scope import decision_for
from src.agents.domain.values import ScopeLabel


@pytest.mark.parametrize(
    "label, utterance",
    [
        (ScopeLabel.OUT_OF_SCOPE, "So sánh với Tesla"),
        (ScopeLabel.OUT_OF_SCOPE, "Giá xe Toyota"),
        (ScopeLabel.OUT_OF_SCOPE, "Tư vấn cổ phiếu"),
        (ScopeLabel.OUT_OF_SCOPE, "Dự báo thời tiết"),
        (ScopeLabel.OUT_OF_SCOPE, "Viết giúp bài tập"),
        (ScopeLabel.OUT_OF_SCOPE, "Đặt vé máy bay"),
        (ScopeLabel.MISSING_DATA, "Chính sách chưa có tài liệu"),
        (ScopeLabel.MISSING_DATA, "Hỏi thông số chưa xác minh"),
        (ScopeLabel.MISSING_DATA, "Xe nào đó nhưng không nói tên"),
        (ScopeLabel.MISSING_DATA, "Giá tương lai chưa công bố"),
        (ScopeLabel.MISSING_DATA, "Khuyến mại không có hiệu lực"),
        (ScopeLabel.MISSING_DATA, "Câu hỏi thiếu mẫu xe cụ thể"),
    ],
)
def test_every_rejected_case_has_limitation_escape_and_complete_response(label: ScopeLabel, utterance: str) -> None:
    decision = decision_for(label=label, utterance=utterance)

    assert decision.label is label
    assert decision.limitation
    assert decision.escape_route
    assert decision.limitation in decision.user_response
    assert decision.escape_route in decision.user_response


def test_in_scope_decision_is_not_rejected() -> None:
    decision = decision_for(label=ScopeLabel.IN_SCOPE, utterance="Tư vấn xe VinFast cho gia đình")

    assert decision.limitation is None
    assert decision.escape_route is None
    assert decision.user_response == ""


@pytest.mark.parametrize("utterance", ["alo", "chào em", "cảm ơn em nhé"])
def test_social_decision_carries_no_rejection_guidance(utterance: str) -> None:
    """Chào hỏi không được mang lời từ chối: gộp vào OUT_OF_SCOPE là khách chào
    một câu thì lượt dừng ngay."""

    decision = decision_for(label=ScopeLabel.SOCIAL, utterance=utterance)

    assert decision.limitation is None
    assert decision.escape_route is None
    assert decision.user_response == ""
