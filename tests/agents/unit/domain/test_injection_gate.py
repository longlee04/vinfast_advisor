"""J1 injection gate: bất biến "judge chỉ thêm chặn, không gỡ kết luận regex"."""

from __future__ import annotations

import pytest

from src.agents.domain.injection_gate import (
    INJECTION_CONFIDENCE_THRESHOLD,
    INJECTION_FULL_COVERAGE_TURNS,
    InjectionFallbackReason,
    InjectionJudgePrediction,
    merge_injection_verdict,
    should_sample_injection,
)


def _predict(is_injection: bool, confidence: float = 1.0) -> InjectionJudgePrediction:
    return InjectionJudgePrediction(is_injection=is_injection, confidence=confidence)


class TestRegexFloor:
    def test_regex_blocked_stays_blocked_even_in_shadow(self) -> None:
        assert merge_injection_verdict(True, _predict(False)) is True

    def test_regex_blocked_ignores_low_confidence_judge(self) -> None:
        assert merge_injection_verdict(True, _predict(False, 0.0)) is True

    def test_regex_blocked_ignores_fail_open_judge(self) -> None:
        assert merge_injection_verdict(True, None) is True


class TestShadowMode:
    def test_shadow_never_adds_block(self) -> None:
        assert merge_injection_verdict(False, _predict(True, 1.0)) is False

    def test_shadow_keeps_regex_floor(self) -> None:
        assert merge_injection_verdict(True, _predict(True, 1.0)) is True


class TestFailOpen:
    def test_missing_prediction_never_blocks(self) -> None:
        assert merge_injection_verdict(False, None) is False


class TestLiveMode:
    def test_confident_injection_blocks(self) -> None:
        assert merge_injection_verdict(False, _predict(True, INJECTION_CONFIDENCE_THRESHOLD), shadow_mode=False) is True

    def test_high_confidence_above_threshold_blocks(self) -> None:
        assert merge_injection_verdict(False, _predict(True, 1.0), shadow_mode=False) is True

    def test_below_threshold_does_not_block(self) -> None:
        assert merge_injection_verdict(False, _predict(True, 0.5), shadow_mode=False) is False

    def test_clean_prediction_does_not_block(self) -> None:
        assert merge_injection_verdict(False, _predict(False, 1.0), shadow_mode=False) is False

    def test_custom_threshold_respected(self) -> None:
        assert merge_injection_verdict(False, _predict(True, 0.95), shadow_mode=False, threshold=0.99) is False


class TestFallbackPrediction:
    def test_fallback_carries_reason(self) -> None:
        prediction = InjectionJudgePrediction(False, 0.0, InjectionFallbackReason.TIMEOUT)
        assert prediction.fallback_reason is InjectionFallbackReason.TIMEOUT


class TestSampling:
    def test_first_turns_always_sampled(self) -> None:
        for turn in range(1, INJECTION_FULL_COVERAGE_TURNS + 1):
            assert should_sample_injection(turn) is True

    @pytest.mark.parametrize("turn", [0, -3])
    def test_non_positive_turn_counts_fall_through_to_random(self, turn: int) -> None:
        assert should_sample_injection(turn) in (True, False)
