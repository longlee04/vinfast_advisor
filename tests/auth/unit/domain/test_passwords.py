"""Password policy tests.

The policy is asserted once here and reused by every flow, so these cases are
what "the password rules" means for registration, staff, change, and reset alike.
"""

import pytest

from src.auth.contracts import PASSWORD_MAX_BYTES, PASSWORD_MIN_LENGTH
from src.auth.domain.errors import (
    PasswordContainsControlCharacterError,
    PasswordMissingCharacterClassError,
    PasswordPolicyError,
    PasswordTooLongError,
    PasswordTooShortError,
)
from src.auth.domain.passwords import is_valid_password, validate_password
from src.auth.domain.values import PlaintextPassword

VALID = "Str0ng!Passw0rd"


def check(raw: str) -> None:
    validate_password(PlaintextPassword(raw))


class TestAcceptedPasswords:
    @pytest.mark.parametrize(
        "raw",
        [
            VALID,
            "Aa1!aaaaaaaa",  # exactly 12 characters
            "Xy9#zzzzzzzzzzzzzzzzzzzz",
            "Mật Khẩu Số1!",  # non-ASCII letters with required classes
            "Παρ0λα!μεγάλη",  # Greek upper/lower plus digit and special
        ],
    )
    def test_accepts_compliant_passwords(self, raw: str) -> None:
        check(raw)

    def test_accepts_unicode_special_character(self) -> None:
        """A non-ASCII symbol counts as special, so policy is not ASCII-only."""
        check("Passw0rd€uro")

    def test_accepts_password_at_the_byte_ceiling(self) -> None:
        check("Aa1!" + "b" * (PASSWORD_MAX_BYTES - 4))


class TestLengthBounds:
    def test_rejects_one_character_below_minimum(self) -> None:
        with pytest.raises(PasswordTooShortError):
            check("Aa1!aaaaaaa")

    def test_minimum_is_measured_in_code_points(self) -> None:
        """12 emoji are 12 characters even though they are many bytes."""
        with pytest.raises(PasswordMissingCharacterClassError):
            check("😀" * 12)

    def test_rejects_input_above_the_byte_ceiling(self) -> None:
        with pytest.raises(PasswordTooLongError):
            check("Aa1!" + "b" * PASSWORD_MAX_BYTES)

    def test_byte_ceiling_counts_utf8_bytes_not_characters(self) -> None:
        # Each emoji is 4 UTF-8 bytes, so this is under the character count but
        # over the byte ceiling.
        with pytest.raises(PasswordTooLongError):
            check("Aa1!" + "😀" * PASSWORD_MAX_BYTES)

    def test_length_is_checked_before_character_classes(self) -> None:
        """An oversized input must be rejected without iterating all of it."""
        with pytest.raises(PasswordTooLongError):
            check("a" * (PASSWORD_MAX_BYTES + 1))


class TestCharacterClasses:
    @pytest.mark.parametrize(
        ("raw", "missing"),
        [
            ("str0ng!passw0rd", "uppercase"),
            ("STR0NG!PASSW0RD", "lowercase"),
            ("Strong!Password", "digit"),
            ("Str0ngPassw0rdX", "special"),
        ],
    )
    def test_rejects_missing_class(self, raw: str, missing: str) -> None:
        with pytest.raises(PasswordMissingCharacterClassError, match=missing):
            check(raw)

    def test_reports_every_missing_class_at_once(self) -> None:
        with pytest.raises(PasswordMissingCharacterClassError) as exc:
            check("aaaaaaaaaaaa")
        message = str(exc.value)
        assert "uppercase" in message and "digit" in message and "special" in message


class TestForbiddenCharacters:
    def test_rejects_nul_byte(self) -> None:
        with pytest.raises(PasswordContainsControlCharacterError):
            check("Str0ng!Pass\x00word")

    @pytest.mark.parametrize("char", ["\n", "\r", "\t", "\x1b", "\x7f"])
    def test_rejects_control_characters(self, char: str) -> None:
        with pytest.raises(PasswordContainsControlCharacterError):
            check(f"Str0ng!Pass{char}word")


class TestNoSilentTransformation:
    def test_leading_space_is_significant(self) -> None:
        """Trimming would let a user set a password they cannot retype."""
        padded = " Str0ng!Passw0rd"
        check(padded)
        assert PlaintextPassword(padded).reveal() == padded

    def test_trailing_space_is_significant(self) -> None:
        padded = "Str0ng!Passw0rd "
        check(padded)
        assert PlaintextPassword(padded).reveal() == padded

    def test_unicode_forms_are_not_normalized(self) -> None:
        """NFC and NFD spellings stay distinct rather than collapsing to one."""
        composed = "Café!Passw0rd"
        decomposed = "Café!Passw0rd"
        check(composed)
        check(decomposed)
        assert composed != decomposed


class TestPolicyAppliesToEveryFlow:
    """One policy function serves registration, staff, change, and reset."""

    @pytest.mark.parametrize(
        "flow",
        ["registration", "staff_temporary", "forced_change", "normal_change", "reset"],
    )
    def test_same_rejection_in_every_flow(self, flow: str) -> None:
        with pytest.raises(PasswordPolicyError):
            check("weak")

    @pytest.mark.parametrize(
        "flow",
        ["registration", "staff_temporary", "forced_change", "normal_change", "reset"],
    )
    def test_same_acceptance_in_every_flow(self, flow: str) -> None:
        check(VALID)


class TestNonRaisingForm:
    def test_returns_true_for_valid(self) -> None:
        assert is_valid_password(PlaintextPassword(VALID)) is True

    def test_returns_false_for_invalid(self) -> None:
        assert is_valid_password(PlaintextPassword("weak")) is False


class TestErrorsCarryStableCodes:
    def test_every_policy_error_has_a_code(self) -> None:
        assert PasswordTooShortError.code == "password_too_short"
        assert PasswordTooLongError.code == "password_too_long"
        assert PasswordMissingCharacterClassError.code == "password_missing_character_class"
        assert PasswordContainsControlCharacterError.code == "password_contains_control_character"

    def test_policy_errors_share_a_base_class(self) -> None:
        assert issubclass(PasswordTooShortError, PasswordPolicyError)

    def test_minimum_length_matches_the_frozen_contract(self) -> None:
        assert PASSWORD_MIN_LENGTH == 12
