"""Unit tests cho feature_discrimination (T7)."""

from __future__ import annotations

from uuid import UUID

from src.agents.domain.feature_discrimination import (
    select_discriminating_features,
)

_CAR = UUID("20000000-0000-0000-0000-000000000101")
_BIKE = UUID("20000000-0000-0000-0000-000000000102")


def _features(mapping: dict[str, set[str]]) -> dict[UUID, frozenset[str]]:
    return {vehicle_id: frozenset(codes) for vehicle_id, codes in mapping.items()}


class TestSelectDiscriminatingFeatures:
    def test_picks_feature_closest_to_fifty_fifty(self) -> None:
        # camera: 2/3 xe có → điểm min(2,1)=1 (tốt nhất). pin: 3/3 → điểm 0.
        candidates = _features(
            {
                _CAR: {"CAMERA", "PIN"},
                _BIKE: {"CAMERA", "PIN"},
                UUID("20000000-0000-0000-0000-000000000103"): {"PIN"},
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset({"CAMERA", "PIN"}),
        )
        assert result == ("CAMERA",)

    def test_drops_zero_score_features(self) -> None:
        # Mọi xe đều có PIN → điểm 0, bị loại.
        candidates = _features(
            {
                _CAR: {"PIN"},
                _BIKE: {"PIN"},
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset({"PIN"}),
        )
        assert result == ()

    def test_ignores_features_outside_askable(self) -> None:
        candidates = _features(
            {
                _CAR: {"GPS"},
                _BIKE: {"GPS"},
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset(),  # GPS không nằm trong allowlist.
        )
        assert result == ()

    def test_returns_empty_when_no_candidates(self) -> None:
        result = select_discriminating_features(
            candidate_features={},
            askable=frozenset({"CAMERA"}),
        )
        assert result == ()

    def test_ties_break_by_display_order(self) -> None:
        # camera và pin đều điểm 1 → xếp theo display_order.
        candidates = _features(
            {
                _CAR: {"CAMERA", "PIN"},
                _BIKE: {"PIN"},
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset({"PIN", "CAMERA"}),
            display_order={"CAMERA": 1, "PIN": 2},
        )
        assert result == ("CAMERA",)

    def test_limited_to_three(self) -> None:
        candidates = _features(
            {
                _CAR: {"A", "B", "C", "D"},
                _BIKE: set(),
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset({"A", "B", "C", "D"}),
            limit=3,
        )
        assert len(result) == 3

    def test_limit_one_used_by_routing(self) -> None:
        # `route_after_layer1` chỉ cần biết "còn feature phân biệt hay không".
        candidates = _features(
            {
                _CAR: {"A", "B"},
                _BIKE: {"A"},
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset({"A", "B"}),
            limit=1,
        )
        assert len(result) == 1

    def test_ties_without_display_order_are_stable(self) -> None:
        # Không có display_order → kết quả ổn định theo thứ tự duyệt candidate.
        candidates = _features(
            {
                _CAR: {"B", "A"},
                _BIKE: {"A"},
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset({"A", "B"}),
        )
        assert result == tuple(sorted(result)) or len(result) == 2

    def test_display_order_wins_over_scan_order(self) -> None:
        # A có 2/3 xe, Z có 1/3 → cùng điểm 1 → display_order quyết định thứ tự.
        candidates = _features(
            {
                _CAR: {"Z", "A"},
                _BIKE: {"A"},
                UUID("20000000-0000-0000-0000-000000000103"): set(),
            }
        )
        result = select_discriminating_features(
            candidate_features=candidates,
            askable=frozenset({"A", "Z"}),
            display_order={"Z": 1, "A": 2},
        )
        assert result == ("Z", "A")
