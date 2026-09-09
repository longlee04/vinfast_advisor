"""J4: xin gặp người gián tiếp — khóa hành vi escalate của `escalation_signals`.

Câu "người có thẩm quyền"/"người quản lý"/"cấp trên" không trúng bản cũ
`_HUMAN_REQUESTS` (chỉ "tư vấn viên/nhân viên/người thật"). Bản J4 bổ sung cụm
gián tiếp có động từ xin gặp, và lock test này giữ chúng không bị gỡ.
"""

from __future__ import annotations

from src.agents.domain.escalation import escalation_signals


class TestIndirectHumanRequests:
    @staticmethod
    def _requests_human(message: str) -> bool:
        return escalation_signals(message)["human_requested"]

    def test_nguoi_co_tham_quyen_escalates(self) -> None:
        assert self._requests_human("cho em nói chuyện với người có thẩm quyền quyết định")

    def test_nguoi_quan_ly_escalates(self) -> None:
        assert self._requests_human("em muốn gặp người quản lý")

    def test_cap_tren_escalates(self) -> None:
        assert self._requests_human("gặp cấp trên của em được không")

    def test_llm_signal_adds_but_never_removes(self) -> None:
        assert escalation_signals("tư vấn giúp em", llm_human_requested=True)["human_requested"] is True

    def test_plain_advisory_without_human_request_stays(self) -> None:
        assert escalation_signals("tư vấn giúp em chọn xe")["human_requested"] is False

    def test_mentions_of_manager_do_not_false_positive(self) -> None:
        assert self._requests_human("ban quản lý không cho sạc dưới hầm") is False
