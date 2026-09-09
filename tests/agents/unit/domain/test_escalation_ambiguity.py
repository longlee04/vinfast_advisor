"""Phân loại hazard theo độ mơ hồ (ENG REVIEW AMENDMENT 1).

Hazard mơ hồ (`đang cháy`, `bị cháy`, `ra khói` — sóng đôi với nghĩa lành
"chạy"/"khơi") chỉ được tin khi khớp ở dạng ORIGINAL (có dấu phân biệt nghĩa)
hoặc khi có corroboration (LLM CRITICAL / human_requested). Khớp folded-only
mà không corroboration thì KHÔNG handoff CRITICAL — nhưng cũng KHÔNG hạ về
ELEVATED-thôi.

Hazard không mơ hồ (`bốc cháy`, `phát nổ`, `mất phanh`, ...) giữ CRITICAL cả
khi khớp folded (không dấu) — không dấu là chế độ gõ phổ biến, không được tắt
handoff khẩn cấp cho đa số input.
"""

from __future__ import annotations

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.escalation import escalation_signals, is_critical_safety_incident
from src.agents.domain.values import Severity


def test_diacritic_chay_the_verb_is_not_fire() -> None:
    """ "xe của tôi đang chạy" (có dấu) — nghĩa lành, KHÔNG handoff CRITICAL.

    Failing-first: code cũ normalize bỏ dấu → "dang chay" trùng hazard → trả
    True. Sau amendment: chỉ khớp folded, không corroboration → False.
    """

    signals = escalation_signals("xe của tôi đang chạy")
    assert signals["critical_safety"] is False
    assert signals["severity"] is not Severity.CRITICAL
    assert is_critical_safety_incident("xe của tôi đang chạy") is False


def test_diacritic_chay_with_llm_corroboration_still_handoffs() -> None:
    """Có dấu "đang chạy" + LLM CRITICAL → corroboration → vẫn handoff."""

    signals = escalation_signals("xe của tôi đang chạy", llm_severity=Severity.CRITICAL)
    assert signals["critical_safety"] is True
    assert signals["severity"] is Severity.CRITICAL


def test_folded_ambiguous_hazard_with_llm_corroboration_still_handoffs() -> None:
    """Không dấu "xe cua toi dang chay" + LLM CRITICAL → VẪN handoff.

    Eval requirement: ambiguity redesign không được phá hướng "không dấu vẫn
    handoff" khi có corroboration.
    """

    signals = escalation_signals("xe cua toi dang chay", llm_severity=Severity.CRITICAL)
    assert signals["critical_safety"] is True
    assert signals["severity"] is Severity.CRITICAL


def test_folded_ambiguous_hazard_with_human_request_corroborates() -> None:
    """Không dấu + human_requested → corroboration → handoff."""

    signals = escalation_signals("xe cua toi dang chay", llm_human_requested=True)
    assert signals["critical_safety"] is True


def test_folded_ambiguous_hazard_without_corroboration_still_handoffs() -> None:
    """Không dấu "xe cua toi dang chay" → khớp ORIGINAL (original không dấu
    chứa thẳng needle folded) → KHÔNG phải "chỉ khớp folded" → handoff luôn.

    Không dấu là chế độ gõ phổ biến — không được tắt handoff khẩn cấp cho đa
    số input (ENG REVIEW AMENDMENT 1). "Chỉ khớp folded" chỉ xảy ra khi original
    CÓ dấu mà từ thật khác hazard — ca đó xem test dưới.
    """

    signals = escalation_signals("xe cua toi dang chay")
    assert signals["critical_safety"] is True
    assert signals["severity"] is Severity.CRITICAL


def test_unambiguous_hazard_folded_stays_critical() -> None:
    """Hazard không mơ hồ khớp folded (không dấu) → giữ CRITICAL, không hạ."""

    assert is_critical_safety_incident("xe toi bi mat phanh") is True
    assert is_critical_safety_incident("xe cua toi boc chay") is True
    assert is_critical_safety_incident("xe toi vua tai nan") is True


def test_diacritic_real_fire_is_critical() -> None:
    """Hazard mơ hồ khớp ORIGINAL (có dấu "đang cháy") → tin cậy, CRITICAL."""

    assert is_critical_safety_incident("xe của tôi đang cháy") is True
    signals = escalation_signals("xe của tôi đang cháy")
    assert signals["critical_safety"] is True
    assert signals["severity"] is Severity.CRITICAL


def test_gate_consumes_canonical_from_state_not_recompute() -> None:
    """Gate đọc canonical từ state — không tự normalize lại.

    Truyền canonical tường minh (như chain sẽ làm) phải cho kết quả y hệt
    đường tự dựng, và không phụ thuộc user_message thô.
    """

    canonical = build_canonical_text("xe của tôi đang chạy")
    signals = escalation_signals("xe của tôi đang chạy", canonical=canonical)
    assert signals["critical_safety"] is False

    canonical_fire = build_canonical_text("xe của tôi đang cháy")
    signals_fire = escalation_signals("xe của tôi đang cháy", canonical=canonical_fire)
    assert signals_fire["critical_safety"] is True
