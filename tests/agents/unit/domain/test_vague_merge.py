"""J3 vague-verdict merge: bất biến "judge chỉ THÊM, không gỡ"."""

from __future__ import annotations

from src.agents.domain.slot_salvage import (
    VAGUE_CONFIDENCE_THRESHOLD,
    VagueFallbackReason,
    VagueJudgePrediction,
    merge_vague_verdict,
)


def _predict(is_vague: bool, confidence: float = 1.0) -> VagueJudgePrediction:
    return VagueJudgePrediction(is_vague=is_vague, confidence=confidence)


class TestMerge:
    def test_regex_vague_stays_vague(self) -> None:
        assert merge_vague_verdict(True, _predict(False)) is True

    def test_shadow_never_adds(self) -> None:
        assert merge_vague_verdict(False, _predict(True, 1.0)) is False

    def test_live_confident_adds(self) -> None:
        assert merge_vague_verdict(False, _predict(True, VAGUE_CONFIDENCE_THRESHOLD), shadow_mode=False) is True

    def test_live_below_threshold_does_not_add(self) -> None:
        assert merge_vague_verdict(False, _predict(True, 0.5), shadow_mode=False) is False

    def test_clean_prediction_does_not_add(self) -> None:
        assert merge_vague_verdict(False, _predict(False, 1.0), shadow_mode=False) is False

    def test_missing_prediction_never_adds(self) -> None:
        assert merge_vague_verdict(False, None, shadow_mode=False) is False


class TestFallbackPrediction:
    def test_fallback_carries_reason(self) -> None:
        prediction = VagueJudgePrediction(False, 0.0, VagueFallbackReason.TIMEOUT)
        assert prediction.fallback_reason is VagueFallbackReason.TIMEOUT
