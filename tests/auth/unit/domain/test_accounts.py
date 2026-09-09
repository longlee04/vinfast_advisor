"""Account lifecycle tests.

The state machine is the single gate deciding who may hold a session, so every
transition and every rejection is asserted here rather than re-derived per flow.
"""

from datetime import UTC, datetime

import pytest

from src.auth.domain.accounts import (
    AccountState,
    User,
    initial_customer_state,
    initial_staff_state,
)
from src.auth.domain.authorization import Role
from src.auth.domain.clock import NaiveDatetimeError
from src.auth.domain.errors import (
    AccountDisabledError,
    AccountNotVerifiedError,
    AccountStateError,
    TemporaryPasswordRequiredError,
)
from src.auth.domain.values import NormalizedEmail, PasswordHash, UserId

NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
HASH = PasswordHash("$argon2id$v=19$m=65536,t=3,p=4$abc$def")
NEW_HASH = PasswordHash("$argon2id$v=19$m=65536,t=3,p=4$xyz$uvw")


def make_user(
    state: AccountState = AccountState.ACTIVE,
    role: Role = Role.CUSTOMER,
    password_hash: PasswordHash = HASH,
) -> User:
    return User(
        id=UserId("u-1"),
        email=NormalizedEmail.parse("user@gmail.com"),
        role=role,
        state=state,
        password_hash=password_hash,
        created_at=NOW,
    )


class TestConstruction:
    def test_builds_an_active_user(self) -> None:
        user = make_user()
        assert user.is_active is True
        assert user.is_disabled is False

    def test_requires_a_password_hash(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(password_hash=PasswordHash(""))

    def test_rejects_naive_created_at(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            User(
                id=UserId("u-1"),
                email=NormalizedEmail.parse("user@gmail.com"),
                role=Role.CUSTOMER,
                state=AccountState.ACTIVE,
                password_hash=HASH,
                created_at=datetime(2026, 7, 29, 12, 0, 0),
            )

    def test_is_immutable(self) -> None:
        """Transitions return new instances, so no flow can half-apply a change."""
        with pytest.raises(Exception):
            setattr(make_user(), "state", AccountState.DISABLED)


class TestInitialStates:
    def test_customer_starts_pending_verification(self) -> None:
        assert initial_customer_state() is AccountState.PENDING_VERIFICATION

    def test_staff_starts_with_a_temporary_password(self) -> None:
        assert initial_staff_state() is AccountState.TEMPORARY_PASSWORD


class TestOnlyActiveMayStartASession:
    def test_active_account_may_start_a_session(self) -> None:
        make_user(AccountState.ACTIVE).assert_can_start_session()

    def test_pending_verification_is_rejected(self) -> None:
        with pytest.raises(AccountNotVerifiedError):
            make_user(AccountState.PENDING_VERIFICATION).assert_can_start_session()

    def test_temporary_password_is_rejected(self) -> None:
        """Staff must replace the temporary credential before normal tokens."""
        with pytest.raises(TemporaryPasswordRequiredError):
            make_user(AccountState.TEMPORARY_PASSWORD).assert_can_start_session()

    def test_disabled_is_rejected(self) -> None:
        with pytest.raises(AccountDisabledError):
            make_user(AccountState.DISABLED).assert_can_start_session()

    @pytest.mark.parametrize("state", list(AccountState))
    def test_every_state_is_classified(self, state: AccountState) -> None:
        user = make_user(state)
        if state is AccountState.ACTIVE:
            user.assert_can_start_session()
        else:
            with pytest.raises(AccountStateError):
                user.assert_can_start_session()

    def test_disabled_takes_precedence_over_unverified(self) -> None:
        """A disabled account must not be told its email is merely unverified."""
        with pytest.raises(AccountDisabledError):
            make_user(AccountState.DISABLED).assert_can_start_session()


class TestEmailVerification:
    def test_pending_becomes_active(self) -> None:
        assert make_user(AccountState.PENDING_VERIFICATION).verify_email().state is AccountState.ACTIVE

    def test_verified_account_cannot_verify_again(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(AccountState.ACTIVE).verify_email()

    def test_disabled_account_cannot_verify(self) -> None:
        with pytest.raises(AccountDisabledError):
            make_user(AccountState.DISABLED).verify_email()

    def test_staff_account_cannot_use_the_verification_path(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(AccountState.TEMPORARY_PASSWORD).verify_email()

    def test_password_hash_is_unchanged(self) -> None:
        assert make_user(AccountState.PENDING_VERIFICATION).verify_email().password_hash == HASH


class TestTemporaryPasswordChange:
    def test_staff_becomes_active_with_the_new_hash(self) -> None:
        user = make_user(AccountState.TEMPORARY_PASSWORD, Role.ADVISOR)
        changed = user.complete_temporary_password_change(NEW_HASH)
        assert changed.state is AccountState.ACTIVE
        assert changed.password_hash == NEW_HASH

    def test_rejects_reusing_the_temporary_hash(self) -> None:
        user = make_user(AccountState.TEMPORARY_PASSWORD, Role.ADVISOR)
        with pytest.raises(AccountStateError):
            user.complete_temporary_password_change(HASH)

    def test_rejects_empty_hash(self) -> None:
        user = make_user(AccountState.TEMPORARY_PASSWORD, Role.ADVISOR)
        with pytest.raises(AccountStateError):
            user.complete_temporary_password_change(PasswordHash(""))

    def test_active_account_cannot_use_this_path(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(AccountState.ACTIVE).complete_temporary_password_change(NEW_HASH)

    def test_disabled_account_cannot_use_this_path(self) -> None:
        with pytest.raises(AccountDisabledError):
            make_user(AccountState.DISABLED).complete_temporary_password_change(NEW_HASH)

    def test_requires_password_change_flag_reflects_state(self) -> None:
        assert make_user(AccountState.TEMPORARY_PASSWORD).requires_password_change is True
        assert make_user(AccountState.ACTIVE).requires_password_change is False


class TestChangePassword:
    def test_active_account_changes_password(self) -> None:
        assert make_user(AccountState.ACTIVE).change_password(NEW_HASH).password_hash == NEW_HASH

    def test_state_is_preserved(self) -> None:
        assert make_user(AccountState.ACTIVE).change_password(NEW_HASH).state is AccountState.ACTIVE

    def test_unverified_account_is_rejected(self) -> None:
        with pytest.raises(AccountNotVerifiedError):
            make_user(AccountState.PENDING_VERIFICATION).change_password(NEW_HASH)

    def test_temporary_password_account_is_routed_elsewhere(self) -> None:
        with pytest.raises(TemporaryPasswordRequiredError):
            make_user(AccountState.TEMPORARY_PASSWORD).change_password(NEW_HASH)

    def test_disabled_account_is_rejected(self) -> None:
        with pytest.raises(AccountDisabledError):
            make_user(AccountState.DISABLED).change_password(NEW_HASH)

    def test_rejects_empty_hash(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(AccountState.ACTIVE).change_password(PasswordHash(""))


class TestResetPassword:
    def test_active_account_resets(self) -> None:
        assert make_user(AccountState.ACTIVE).reset_password(NEW_HASH).password_hash == NEW_HASH

    def test_reset_also_completes_verification(self) -> None:
        """Proving mailbox control is the same evidence verification asks for."""
        user = make_user(AccountState.PENDING_VERIFICATION)
        assert user.reset_password(NEW_HASH).state is AccountState.ACTIVE

    def test_reset_clears_a_temporary_password_state(self) -> None:
        user = make_user(AccountState.TEMPORARY_PASSWORD, Role.ADVISOR)
        assert user.reset_password(NEW_HASH).state is AccountState.ACTIVE

    def test_disabled_account_cannot_reset(self) -> None:
        with pytest.raises(AccountDisabledError):
            make_user(AccountState.DISABLED).reset_password(NEW_HASH)

    def test_rejects_empty_hash(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(AccountState.ACTIVE).reset_password(PasswordHash(""))


class TestDisableAndEnable:
    @pytest.mark.parametrize(
        "state",
        [AccountState.ACTIVE, AccountState.PENDING_VERIFICATION, AccountState.TEMPORARY_PASSWORD],
    )
    def test_any_live_state_can_be_disabled(self, state: AccountState) -> None:
        assert make_user(state).disable().state is AccountState.DISABLED

    def test_disabling_twice_is_rejected(self) -> None:
        with pytest.raises(AccountDisabledError):
            make_user(AccountState.DISABLED).disable()

    def test_disabled_account_can_be_enabled(self) -> None:
        assert make_user(AccountState.DISABLED).enable().state is AccountState.ACTIVE

    def test_enable_can_target_a_temporary_password_state(self) -> None:
        user = make_user(AccountState.DISABLED, Role.ADVISOR)
        assert user.enable(state=AccountState.TEMPORARY_PASSWORD).state is AccountState.TEMPORARY_PASSWORD

    def test_enable_cannot_target_disabled(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(AccountState.DISABLED).enable(state=AccountState.DISABLED)

    def test_only_a_disabled_account_can_be_enabled(self) -> None:
        with pytest.raises(AccountStateError):
            make_user(AccountState.ACTIVE).enable()

    def test_enable_preserves_the_password_hash(self) -> None:
        """Re-enabling restores access, it does not rotate the credential."""
        assert make_user(AccountState.DISABLED).enable().password_hash == HASH

    def test_disable_preserves_identity_and_role(self) -> None:
        user = make_user(AccountState.ACTIVE, Role.ADVISOR)
        disabled = user.disable()
        assert disabled.id == user.id
        assert disabled.email == user.email
        assert disabled.role is Role.ADVISOR
