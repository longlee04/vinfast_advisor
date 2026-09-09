"""Time policy tests.

Expiry is checked at microsecond boundaries because "expired" is the difference
between accepting and rejecting a credential, and an off-by-one-tick rule is
exactly the kind of bug that never shows up in a coarse test.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.auth.domain.clock import (
    FixedClock,
    NaiveDatetimeError,
    ensure_utc,
    expires_after,
    is_expired,
)
from src.auth.infrastructure.clock import SystemClock

MOMENT = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)


class TestEnsureUtc:
    def test_accepts_utc_datetime(self) -> None:
        assert ensure_utc(MOMENT) == MOMENT

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            ensure_utc(datetime(2026, 7, 29, 12, 0, 0))

    def test_converts_other_offsets_to_utc(self) -> None:
        saigon = datetime(2026, 7, 29, 19, 0, 0, tzinfo=timezone(timedelta(hours=7)))
        assert ensure_utc(saigon) == MOMENT

    def test_result_is_always_utc(self) -> None:
        saigon = datetime(2026, 7, 29, 19, 0, 0, tzinfo=timezone(timedelta(hours=7)))
        assert ensure_utc(saigon).tzinfo == UTC


class TestExpiryBoundary:
    def test_one_microsecond_before_expiry_is_valid(self) -> None:
        assert is_expired(MOMENT - timedelta(microseconds=1), MOMENT) is False

    def test_exact_expiry_is_expired(self) -> None:
        """Validity is `now < expires_at`, so the stated instant is already out."""
        assert is_expired(MOMENT, MOMENT) is True

    def test_one_microsecond_after_expiry_is_expired(self) -> None:
        assert is_expired(MOMENT + timedelta(microseconds=1), MOMENT) is True

    def test_naive_now_is_rejected(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            is_expired(datetime(2026, 7, 29, 12, 0, 0), MOMENT)

    def test_naive_expiry_is_rejected(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            is_expired(MOMENT, datetime(2026, 7, 29, 12, 0, 0))

    def test_negative_replica_skew_does_not_expire_early(self) -> None:
        """A replica running behind must not treat a live credential as expired."""
        assert is_expired(MOMENT - timedelta(seconds=30), MOMENT) is False


class TestExpiresAfter:
    def test_adds_ttl_in_utc(self) -> None:
        assert expires_after(MOMENT, 3600) == MOMENT + timedelta(hours=1)

    @pytest.mark.parametrize("ttl", [0, -1])
    def test_rejects_non_positive_ttl(self, ttl: int) -> None:
        with pytest.raises(ValueError):
            expires_after(MOMENT, ttl)

    def test_rejects_naive_now(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            expires_after(datetime(2026, 7, 29), 60)


class TestFixedClock:
    def test_returns_the_pinned_instant(self) -> None:
        assert FixedClock(MOMENT).now() == MOMENT

    def test_repeated_reads_are_identical(self) -> None:
        clock = FixedClock(MOMENT)
        assert clock.now() == clock.now()

    def test_advance_moves_time_forward(self) -> None:
        clock = FixedClock(MOMENT)
        clock.advance(90)
        assert clock.now() == MOMENT + timedelta(seconds=90)

    def test_rejects_naive_construction(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            FixedClock(datetime(2026, 7, 29))


class TestSystemClock:
    def test_returns_timezone_aware_utc(self) -> None:
        assert SystemClock().now().tzinfo == UTC
