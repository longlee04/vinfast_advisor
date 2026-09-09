"""Unit tests for range_period normalization."""

from math import ceil

from src.agents.domain.range_normalizer import (
    MAX_PLAUSIBLE_DAILY_KM,
    RangePeriod,
    normalize_range_km,
)


class TestNormalizeRangeKm:
    """Quy đổi quãng đường theo đơn vị thời gian về km/ngày."""

    def test_month_1200_becomes_40(self) -> None:
        assert normalize_range_km(1200, "month") == (40, None)

    def test_week_300_becomes_43(self) -> None:
        assert normalize_range_km(300, "week") == (ceil(300 / 7), None)
        assert normalize_range_km(300, "week") == (43, None)

    def test_day_500_above_ceiling_rejected(self) -> None:
        value, reason = normalize_range_km(500, "day")
        assert value is None
        assert reason is not None

    def test_none_period_kept(self) -> None:
        assert normalize_range_km(30, None) == (30, None)

    def test_day_30_kept(self) -> None:
        assert normalize_range_km(30, "day") == (30, None)

    def test_trip_rejected_with_reason(self) -> None:
        value, reason = normalize_range_km(80, "trip")
        assert value is None
        assert reason is not None

    def test_day_300_at_boundary_accepted(self) -> None:
        assert normalize_range_km(300, "day") == (300, None)

    def test_day_301_above_boundary_rejected(self) -> None:
        value, reason = normalize_range_km(301, "day")
        assert value is None
        assert reason is not None

    def test_unknown_period_treated_as_day(self) -> None:
        assert normalize_range_km(30, "century") == (30, None)

    def test_week_rounds_up(self) -> None:
        assert normalize_range_km(1, "week") == (1, None)

    def test_month_rounds_up(self) -> None:
        # 1000/30 = 33.33 → ceil = 34.
        assert normalize_range_km(1000, "month") == (34, None)

    def test_ceiling_applies_after_normalization(self) -> None:
        # 2107 km/tuần = 301 km/ngày — vượt ngưỡng SAU quy đổi → loại.
        value, reason = normalize_range_km(2107, "week")
        assert value is None
        assert reason is not None
        # 2100 km/tuần = 300 km/ngày — đúng biên → giữ.
        assert normalize_range_km(2100, "week") == (300, None)

    def test_max_plausible_constant(self) -> None:
        assert MAX_PLAUSIBLE_DAILY_KM == 300


class TestRangePeriod:
    def test_enum_values(self) -> None:
        assert {p.value for p in RangePeriod} == {"day", "week", "month", "trip"}
