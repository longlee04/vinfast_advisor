"""Refresh-family and one-time-token policy tests.

Rotation, replay, and revocation scope are the parts of Auth where a subtle
mistake is silently exploitable, so each invariant is asserted directly:
exactly-one successor, absolute expiry never extended, replay kills one family,
and one-time tokens are purpose-bound and single-use.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.auth.domain.clock import NaiveDatetimeError
from src.auth.domain.errors import (
    RefreshTokenReplayError,
    SessionExpiredError,
    SessionRevokedError,
    TokenAlreadyConsumedError,
    TokenExpiredError,
    TokenPurposeMismatchError,
)
from src.auth.domain.sessions import (
    OneTimeToken,
    RefreshToken,
    RevocationReason,
    TokenPurpose,
    revoke_all_families,
    revoke_family,
)
from src.auth.domain.values import FamilyId, SessionId, TokenHash, UserId

NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
FAMILY_EXPIRY = NOW + timedelta(days=30)
USER = UserId("u-1")


def make_refresh(
    token_hash: str = "hash-1",
    session_id: str = "s-1",
    family_id: str = "f-1",
    issued_at: datetime = NOW,
    family_expires_at: datetime = FAMILY_EXPIRY,
) -> RefreshToken:
    return RefreshToken(
        token_hash=TokenHash(token_hash),
        session_id=SessionId(session_id),
        family_id=FamilyId(family_id),
        user_id=USER,
        issued_at=issued_at,
        family_expires_at=family_expires_at,
    )


def make_one_time(
    purpose: TokenPurpose = TokenPurpose.EMAIL_VERIFICATION,
    ttl: timedelta = timedelta(hours=24),
    user_id: UserId = USER,
) -> OneTimeToken:
    return OneTimeToken(
        token_hash=TokenHash("token-hash"),
        purpose=purpose,
        user_id=user_id,
        issued_at=NOW,
        expires_at=NOW + ttl,
    )


class TestRefreshTokenConstruction:
    def test_builds_a_usable_token(self) -> None:
        token = make_refresh()
        assert token.is_revoked is False
        token.assert_usable(NOW)

    def test_requires_a_hash(self) -> None:
        with pytest.raises(ValueError):
            make_refresh(token_hash="")

    def test_rejects_naive_issued_at(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            make_refresh(issued_at=datetime(2026, 7, 29, 12, 0, 0))

    def test_rejects_naive_family_expiry(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            make_refresh(family_expires_at=datetime(2026, 8, 28, 12, 0, 0))


class TestRotationProducesExactlyOneSuccessor:
    def test_current_token_is_revoked_as_rotated(self) -> None:
        revoked, _ = make_refresh().rotate(NOW, TokenHash("hash-2"))
        assert revoked.is_revoked is True
        assert revoked.revocation_reason is RevocationReason.ROTATED

    def test_successor_keeps_session_and_family(self) -> None:
        _, successor = make_refresh().rotate(NOW, TokenHash("hash-2"))
        assert successor.session_id == SessionId("s-1")
        assert successor.family_id == FamilyId("f-1")
        assert successor.user_id == USER

    def test_successor_is_not_revoked(self) -> None:
        _, successor = make_refresh().rotate(NOW, TokenHash("hash-2"))
        assert successor.is_revoked is False

    def test_successor_hash_must_differ(self) -> None:
        with pytest.raises(ValueError):
            make_refresh().rotate(NOW, TokenHash("hash-1"))

    def test_successor_hash_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError):
            make_refresh().rotate(NOW, TokenHash(""))

    def test_successor_issued_at_is_the_rotation_instant(self) -> None:
        later = NOW + timedelta(days=5)
        _, successor = make_refresh().rotate(later, TokenHash("hash-2"))
        assert successor.issued_at == later


class TestRotationNeverExtendsAbsoluteExpiry:
    def test_successor_inherits_the_family_deadline(self) -> None:
        _, successor = make_refresh().rotate(NOW + timedelta(days=10), TokenHash("hash-2"))
        assert successor.family_expires_at == FAMILY_EXPIRY

    def test_repeated_rotation_never_moves_the_deadline(self) -> None:
        """Otherwise a live token could be refreshed forever past 30 days."""
        token = make_refresh()
        for index in range(5):
            _, token = token.rotate(NOW + timedelta(days=index + 1), TokenHash(f"hash-{index + 2}"))
        assert token.family_expires_at == FAMILY_EXPIRY

    def test_rotation_after_absolute_expiry_is_refused(self) -> None:
        with pytest.raises(SessionExpiredError):
            make_refresh().rotate(FAMILY_EXPIRY, TokenHash("hash-2"))


class TestReplayDetection:
    def test_presenting_a_rotated_token_is_a_replay(self) -> None:
        revoked, _ = make_refresh().rotate(NOW, TokenHash("hash-2"))
        with pytest.raises(RefreshTokenReplayError):
            revoked.assert_usable(NOW)

    def test_rotating_a_rotated_token_is_a_replay(self) -> None:
        revoked, _ = make_refresh().rotate(NOW, TokenHash("hash-2"))
        with pytest.raises(RefreshTokenReplayError):
            revoked.rotate(NOW, TokenHash("hash-3"))

    def test_replay_is_distinguished_from_ordinary_revocation(self) -> None:
        """Only a rotated-then-reused token indicates a leaked credential."""
        logged_out = make_refresh().revoke(NOW, RevocationReason.LOGOUT)
        with pytest.raises(SessionRevokedError):
            logged_out.assert_usable(NOW)
        assert not isinstance(SessionRevokedError(), RefreshTokenReplayError)

    def test_rotation_reason_survives_a_later_sweep(self) -> None:
        """Replay evidence must not be overwritten by a subsequent logout-all."""
        revoked, _ = make_refresh().rotate(NOW, TokenHash("hash-2"))
        swept = revoked.revoke(NOW + timedelta(minutes=1), RevocationReason.LOGOUT_ALL)
        assert swept.revocation_reason is RevocationReason.ROTATED


class TestRevocationScope:
    def test_expired_family_is_rejected_at_exact_expiry(self) -> None:
        with pytest.raises(SessionExpiredError):
            make_refresh().assert_usable(FAMILY_EXPIRY)

    def test_family_is_valid_one_microsecond_before_expiry(self) -> None:
        make_refresh().assert_usable(FAMILY_EXPIRY - timedelta(microseconds=1))

    def test_revoke_family_revokes_every_token(self) -> None:
        tokens = (make_refresh("h1"), make_refresh("h2"))
        revoked = revoke_family(tokens, NOW, RevocationReason.REPLAY_DETECTED)
        assert all(token.is_revoked for token in revoked)

    def test_revoke_family_records_the_reason(self) -> None:
        revoked = revoke_family((make_refresh(),), NOW, RevocationReason.REPLAY_DETECTED)
        assert revoked[0].revocation_reason is RevocationReason.REPLAY_DETECTED

    def test_revoking_all_families_covers_multiple_devices(self) -> None:
        phone = make_refresh("h1", session_id="s-1", family_id="f-1")
        laptop = make_refresh("h2", session_id="s-2", family_id="f-2")
        revoked = revoke_all_families((phone, laptop), NOW, RevocationReason.PASSWORD_RESET)
        assert {token.family_id for token in revoked} == {FamilyId("f-1"), FamilyId("f-2")}
        assert all(token.is_revoked for token in revoked)

    def test_second_device_family_is_untouched_by_the_first(self) -> None:
        """Replay on one device must not log the user out everywhere."""
        laptop = make_refresh("h2", session_id="s-2", family_id="f-2")
        revoke_family((make_refresh("h1"),), NOW, RevocationReason.REPLAY_DETECTED)
        laptop.assert_usable(NOW)

    def test_revoke_is_idempotent(self) -> None:
        first = make_refresh().revoke(NOW, RevocationReason.LOGOUT)
        second = first.revoke(NOW + timedelta(minutes=5), RevocationReason.LOGOUT_ALL)
        assert second.revoked_at == first.revoked_at
        assert second.revocation_reason is RevocationReason.LOGOUT


class TestOneTimeTokenUsage:
    def test_valid_token_is_usable(self) -> None:
        make_one_time().assert_usable(NOW, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)

    def test_consume_marks_the_token_used(self) -> None:
        consumed = make_one_time().consume(NOW, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)
        assert consumed.is_consumed is True
        assert consumed.consumed_at == NOW

    def test_second_consume_is_rejected(self) -> None:
        consumed = make_one_time().consume(NOW, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)
        with pytest.raises(TokenAlreadyConsumedError):
            consumed.consume(NOW, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)

    def test_requires_a_hash(self) -> None:
        with pytest.raises(ValueError):
            OneTimeToken(
                token_hash=TokenHash(""),
                purpose=TokenPurpose.EMAIL_VERIFICATION,
                user_id=USER,
                issued_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            )


class TestOneTimeTokenBinding:
    def test_wrong_purpose_is_rejected(self) -> None:
        """A reset token can never be spent as a verification token."""
        reset = make_one_time(TokenPurpose.PASSWORD_RESET, ttl=timedelta(hours=1))
        with pytest.raises(TokenPurposeMismatchError):
            reset.consume(NOW, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)

    def test_wrong_user_is_rejected(self) -> None:
        with pytest.raises(TokenPurposeMismatchError):
            make_one_time().consume(NOW, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=UserId("u-2"))

    def test_purpose_is_checked_before_expiry(self) -> None:
        """Cross-purpose use must fail as a mismatch regardless of timing."""
        reset = make_one_time(TokenPurpose.PASSWORD_RESET, ttl=timedelta(hours=1))
        with pytest.raises(TokenPurposeMismatchError):
            reset.consume(NOW + timedelta(days=2), purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)


class TestOneTimeTokenExpiry:
    def test_valid_one_microsecond_before_expiry(self) -> None:
        token = make_one_time(ttl=timedelta(hours=1))
        token.assert_usable(
            NOW + timedelta(hours=1) - timedelta(microseconds=1),
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            user_id=USER,
        )

    def test_expired_at_exact_expiry(self) -> None:
        token = make_one_time(ttl=timedelta(hours=1))
        with pytest.raises(TokenExpiredError):
            token.consume(NOW + timedelta(hours=1), purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)

    def test_verification_ttl_is_24_hours(self) -> None:
        token = make_one_time(ttl=timedelta(hours=24))
        token.assert_usable(
            NOW + timedelta(hours=23, minutes=59),
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            user_id=USER,
        )

    def test_reset_ttl_is_one_hour(self) -> None:
        token = make_one_time(TokenPurpose.PASSWORD_RESET, ttl=timedelta(hours=1))
        with pytest.raises(TokenExpiredError):
            token.consume(
                NOW + timedelta(hours=1, seconds=1),
                purpose=TokenPurpose.PASSWORD_RESET,
                user_id=USER,
            )


class TestLatestTokenWins:
    def test_superseded_token_cannot_be_consumed(self) -> None:
        superseded = make_one_time().supersede(NOW + timedelta(minutes=5))
        with pytest.raises(TokenAlreadyConsumedError):
            superseded.consume(NOW + timedelta(minutes=6), purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)

    def test_supersede_records_the_instant(self) -> None:
        moment = NOW + timedelta(minutes=5)
        assert make_one_time().supersede(moment).superseded_at == moment

    def test_consumed_token_stays_consumed_not_superseded(self) -> None:
        """The consumed record is the audit trail that the credential was spent."""
        consumed = make_one_time().consume(NOW, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=USER)
        assert consumed.supersede(NOW + timedelta(minutes=1)).superseded_at is None

    def test_supersede_is_idempotent(self) -> None:
        first = make_one_time().supersede(NOW + timedelta(minutes=1))
        second = first.supersede(NOW + timedelta(minutes=2))
        assert second.superseded_at == first.superseded_at


class TestEnumContracts:
    def test_token_purposes_have_stable_values(self) -> None:
        assert {p.value for p in TokenPurpose} == {"email_verification", "password_reset"}

    def test_revocation_reasons_are_unique(self) -> None:
        values = [reason.value for reason in RevocationReason]
        assert len(values) == len(set(values))

    def test_rotation_reason_exists_for_replay_detection(self) -> None:
        assert RevocationReason.ROTATED.value == "rotated"
        assert RevocationReason.REPLAY_DETECTED.value == "replay_detected"
