"""J2 risk-flag merge: bất biến "judge chỉ THÊM cờ (OR), không gỡ"."""

from __future__ import annotations

from src.agents.domain.quote_risk import (
    RISK_FLAG_CONFIDENCE_THRESHOLD,
    RiskFlagFallbackReason,
    RiskFlagPrediction,
    merge_risk_flags,
)

_FLAGS = ("is_negotiated", "has_non_standard_offer", "has_financial_commitment", "is_personalized")


def _predict(*, confidence: float = 1.0, **flags: bool) -> RiskFlagPrediction:
    return RiskFlagPrediction(flags=flags, confidence=confidence)


class TestMergeOrOnly:
    def test_regex_true_stays_true_even_with_clean_judge(self) -> None:
        regex = {"is_negotiated": True, **{name: False for name in _FLAGS[1:]}}
        merged = merge_risk_flags(regex, _predict(), shadow_mode=False)
        assert merged["is_negotiated"] is True

    def test_judge_true_adds_flag_in_live_mode(self) -> None:
        regex = {name: False for name in _FLAGS}
        merged = merge_risk_flags(regex, _predict(is_negotiated=True), shadow_mode=False)
        assert merged["is_negotiated"] is True

    def test_judge_cannot_remove_regex_flag(self) -> None:
        regex = {
            "has_financial_commitment": True,
            **{name: False for name in _FLAGS if name != "has_financial_commitment"},
        }
        merged = merge_risk_flags(regex, _predict(has_financial_commitment=False), shadow_mode=False)
        assert merged["has_financial_commitment"] is True


class TestShadowAndFailOpen:
    def test_shadow_never_adds_flags(self) -> None:
        regex = {name: False for name in _FLAGS}
        merged = merge_risk_flags(regex, _predict(is_negotiated=True))
        assert merged == regex

    def test_missing_prediction_keeps_regex(self) -> None:
        regex = {"is_personalized": False, **{name: False for name in _FLAGS[1:]}}
        assert merge_risk_flags(regex, None) == regex

    def test_below_threshold_does_not_add(self) -> None:
        regex = {name: False for name in _FLAGS}
        merged = merge_risk_flags(
            regex,
            _predict(confidence=RISK_FLAG_CONFIDENCE_THRESHOLD - 0.1, is_negotiated=True),
            shadow_mode=False,
        )
        assert merged == regex

    def test_unknown_flag_stays_unknown(self) -> None:
        regex = {name: None for name in _FLAGS}
        merged = merge_risk_flags(regex, _predict(is_negotiated=False), shadow_mode=False)
        assert merged == regex


class TestFallbackPrediction:
    def test_fallback_carries_reason(self) -> None:
        prediction = RiskFlagPrediction(
            flags={name: False for name in _FLAGS},
            confidence=0.0,
            fallback_reason=RiskFlagFallbackReason.TIMEOUT,
        )
        assert prediction.fallback_reason is RiskFlagFallbackReason.TIMEOUT
