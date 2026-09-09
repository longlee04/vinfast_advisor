"""Unit tests for human advisor request detection and scope override."""

from __future__ import annotations

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.values import ScopeLabel
from src.agents.services.intent_heuristics import is_direct_human_request
from src.agents.services.scope_classifier import _apply_quote_risk_override


@pytest.mark.parametrize(
    "message",
    [
        "toi muon gap quan tri vien",
        "toi muon gap tu van vien",
        "chuyển sang tư vấn viên.",
        "chuyen sang tu van vien",
        "cho toi gap tu van vien",
        "gap admin",
        "gap quan tri",
        "noi chuyen voi nguoi that",
        "gap sale",
        "cho toi gap quan tri vien",
        "lien he nhan vien",
        "chuyen sang tu van",
        "chuyen qua tu van vien",
        "chuyen cho tu van vien",
        "noi chuyen voi tu van vien",
    ],
)
def test_is_direct_human_request_detects_all_advisor_and_staff_variants(message: str) -> None:
    assert is_direct_human_request(message, build_canonical_text(message)) is True


def test_scope_override_upgrades_human_request_to_in_scope() -> None:
    label, reason = _apply_quote_risk_override(
        ScopeLabel.OUT_OF_SCOPE, "chuyển sang tư vấn viên.", build_canonical_text("chuyển sang tư vấn viên.")
    )
    assert label == ScopeLabel.IN_SCOPE
    assert reason is not None
    assert "human handoff" in reason.lower()
