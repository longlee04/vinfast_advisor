"""Password policy shared by every credential flow.

One policy object serves customer registration, staff temporary passwords, the
forced first change, ordinary changes, and reset. A second implementation would
eventually drift, and a weaker path is the one an attacker uses.

Deliberate choices:

* Passwords are never trimmed or Unicode-normalized. `" pw"` and `"pw"` are
  different passwords; silently trimming would let a user set a credential they
  cannot reproduce, and normalizing would map distinct inputs onto one hash.
* Length is measured in Unicode code points for the minimum (what a user
  perceives) and in UTF-8 bytes for the maximum (what the hasher must bound).
* Breach-list and password-history screening are explicitly out of scope for
  MVP; adding either is a plan change, not a quiet extension here.
"""

import unicodedata
from typing import Final

from src.auth.contracts import PASSWORD_MAX_BYTES, PASSWORD_MIN_LENGTH
from src.auth.domain.errors import (
    PasswordContainsControlCharacterError,
    PasswordMissingCharacterClassError,
    PasswordTooLongError,
    PasswordTooShortError,
)
from src.auth.domain.values import PlaintextPassword

# Categories that must never appear in a password. NUL terminates C strings and
# can truncate a credential inside a native hashing library; other control
# characters are unreproducible by a user and usually a paste accident.
_FORBIDDEN_CATEGORIES: Final[frozenset[str]] = frozenset({"Cc", "Cs", "Zl", "Zp"})

# A "special" character is anything that is not a letter, digit, or mark. That
# admits Unicode punctuation and symbols rather than only ASCII specials, so a
# non-English speaker is not pushed toward a weaker password.
_LETTER_CATEGORIES: Final[frozenset[str]] = frozenset({"Lu", "Ll", "Lt", "Lm", "Lo"})
_DIGIT_CATEGORIES: Final[frozenset[str]] = frozenset({"Nd", "Nl", "No"})
_MARK_CATEGORIES: Final[frozenset[str]] = frozenset({"Mn", "Mc", "Me"})


def _has_uppercase(password: str) -> bool:
    return any(unicodedata.category(char) == "Lu" or char.isupper() for char in password)


def _has_lowercase(password: str) -> bool:
    return any(unicodedata.category(char) == "Ll" or char.islower() for char in password)


def _has_digit(password: str) -> bool:
    return any(unicodedata.category(char) in _DIGIT_CATEGORIES for char in password)


def _has_special(password: str) -> bool:
    for char in password:
        category = unicodedata.category(char)
        if category in _LETTER_CATEGORIES or category in _DIGIT_CATEGORIES:
            continue
        if category in _MARK_CATEGORIES:
            continue
        return True
    return False


def validate_password(password: PlaintextPassword) -> None:
    """Raise a typed `PasswordPolicyError` subclass unless the password complies.

    Checks run cheapest-first and length before character classes, so an
    oversized input is rejected before anything iterates it.
    """
    raw = password.reveal()

    if len(raw.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise PasswordTooLongError(f"password must be at most {PASSWORD_MAX_BYTES} bytes")
    if len(raw) < PASSWORD_MIN_LENGTH:
        raise PasswordTooShortError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")

    for char in raw:
        if char == "\x00" or unicodedata.category(char) in _FORBIDDEN_CATEGORIES:
            raise PasswordContainsControlCharacterError("password must not contain NUL or control characters")

    missing: list[str] = []
    if not _has_uppercase(raw):
        missing.append("uppercase")
    if not _has_lowercase(raw):
        missing.append("lowercase")
    if not _has_digit(raw):
        missing.append("digit")
    if not _has_special(raw):
        missing.append("special")
    if missing:
        raise PasswordMissingCharacterClassError(f"password must contain at least one {', '.join(missing)} character")


def is_valid_password(password: PlaintextPassword) -> bool:
    """Non-raising form of `validate_password`, for tests and matrix checks."""
    try:
        validate_password(password)
    except (
        PasswordTooLongError,
        PasswordTooShortError,
        PasswordContainsControlCharacterError,
        PasswordMissingCharacterClassError,
    ):
        return False
    return True
