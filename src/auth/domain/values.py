"""Auth value objects.

Two rules drive this module:

* One canonical `NormalizedEmail`. Registration, login, staff creation, CLI
  bootstrap, verification and recovery all normalize through the same function,
  so a database uniqueness constraint on the normalized value cannot disagree
  with an application lookup.
* Plaintext secrets never render. `PlaintextSecret` redacts `repr`/`str` and has
  no serialization support, so a log line, exception, or debug dump cannot
  disclose a password or a raw token (`AGENTS.md:43`).

Deliberately NOT done: Gmail dot and plus canonicalization. `a.b@gmail.com` and
`ab@gmail.com` stay distinct identities. Collapsing them would silently merge
accounts a user considers separate, and no requirement asks for it.
"""

import unicodedata
from dataclasses import dataclass
from typing import Final, NewType, NoReturn

from src.auth.domain.errors import EmailDomainNotAllowedError, InvalidEmailError

UserId = NewType("UserId", str)
SessionId = NewType("SessionId", str)
FamilyId = NewType("FamilyId", str)
PasswordHash = NewType("PasswordHash", str)
TokenHash = NewType("TokenHash", str)

#: Các nhà thư khách hay dùng. Đây là MẶC ĐỊNH, không phải luật cứng: triển khai
#: đổi được qua `AUTH_CUSTOMER_EMAIL_DOMAINS`. Giữ một danh sách trắng thay vì
#: nhận mọi domain là để chặn địa chỉ dùng-một-lần; nới thì thêm tên vào biến
#: môi trường, không phải sửa code.
CUSTOMER_EMAIL_DOMAINS: Final[frozenset[str]] = frozenset(
    {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com"}
)
MAX_EMAIL_LENGTH: Final[int] = 254
MAX_EMAIL_LOCAL_LENGTH: Final[int] = 64

# Zero-width and BOM characters are invisible: `str.strip()` leaves them, and a
# user copying an address from a document can carry them in. Treated as edge
# whitespace so two visually identical addresses normalize identically.
_INVISIBLE_EDGE_CHARS: Final[str] = "​‌‍⁠﻿"


def _strip_edges(raw: str) -> str:
    """Strip Unicode whitespace plus invisible formatting characters."""
    previous = ""
    current = raw
    while current != previous:
        previous = current
        current = current.strip().strip(_INVISIBLE_EDGE_CHARS)
    return current


def _reject_hidden_characters(value: str) -> None:
    for char in value:
        category = unicodedata.category(char)
        # Cc control, Cf format, Zs/Zl/Zp separators, Cs surrogate.
        if category in {"Cc", "Cf", "Cs", "Zs", "Zl", "Zp"}:
            raise InvalidEmailError("email must not contain whitespace or control characters")


@dataclass(frozen=True, slots=True)
class NormalizedEmail:
    """A trimmed, lowercased email address used as the canonical identity key.

    Construct through `parse` or `parse_customer`, never by calling the
    constructor with an unnormalized string.
    """

    value: str

    def __str__(self) -> str:
        return self.value

    @property
    def domain(self) -> str:
        return self.value.rsplit("@", 1)[1]

    @property
    def local_part(self) -> str:
        return self.value.rsplit("@", 1)[0]

    @classmethod
    def parse(cls, raw: str) -> "NormalizedEmail":
        """Normalize any email address, regardless of provider."""
        if not isinstance(raw, str):
            raise InvalidEmailError("email must be a string")
        candidate = _strip_edges(raw)
        if not candidate:
            raise InvalidEmailError("email must not be empty")
        _reject_hidden_characters(candidate)

        if candidate.count("@") != 1:
            raise InvalidEmailError("email must contain exactly one '@'")
        local, domain = candidate.split("@")
        if not local or not domain:
            raise InvalidEmailError("email must have a local part and a domain")
        if len(candidate) > MAX_EMAIL_LENGTH:
            raise InvalidEmailError(f"email must be at most {MAX_EMAIL_LENGTH} characters")
        if len(local) > MAX_EMAIL_LOCAL_LENGTH:
            raise InvalidEmailError(f"email local part must be at most {MAX_EMAIL_LOCAL_LENGTH} characters")
        if "." not in domain or domain.startswith(".") or domain.endswith(".") or ".." in domain:
            raise InvalidEmailError("email domain is not valid")

        # Lowercase both parts. The local part is technically case-sensitive per
        # RFC 5321, but every provider this project targets treats it as
        # case-insensitive, and one casing rule is what makes the database
        # uniqueness constraint match application lookups.
        return cls(f"{local.lower()}@{domain.lower()}")

    @classmethod
    def parse_customer(cls, raw: str, *, allowed_domains: frozenset[str] | None = None) -> "NormalizedEmail":
        """Normalize a customer address, whose domain must be in the allowlist.

        `allowed_domains` đến từ cấu hình triển khai; bỏ trống thì dùng
        `CUSTOMER_EMAIL_DOMAINS`. Danh sách rỗng KHÔNG có nghĩa là mở cửa —
        nó rơi về mặc định, vì một biến môi trường gõ sai không được lặng lẽ
        biến thành "nhận mọi domain".
        """
        email = cls.parse(raw)
        domains = allowed_domains or CUSTOMER_EMAIL_DOMAINS
        if email.domain not in domains:
            allowed = ", ".join(sorted(domains))
            raise EmailDomainNotAllowedError(f"customer email domain must be one of: {allowed}")
        return email


class PlaintextSecret:
    """Holds a plaintext credential and refuses to render it.

    Python cannot guarantee erasure of an immutable `str` from memory, so this
    wrapper bounds *disclosure*, not lifetime: it removes the accidental paths
    (logging, f-strings, tracebacks, debug dumps) rather than claiming the value
    is unrecoverable.
    """

    __slots__ = ("_value",)

    _REDACTED = "***redacted***"

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("secret value must be a string")
        self._value = value

    def reveal(self) -> str:
        """Return the plaintext. Call only at a hashing or delivery boundary."""
        return self._value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._REDACTED})"

    def __str__(self) -> str:
        return self._REDACTED

    def __format__(self, format_spec: str) -> str:
        return self._REDACTED

    def __eq__(self, other: object) -> bool:
        # Deliberately identity-free and not constant-time: comparing plaintext
        # secrets is not part of any flow. Verification compares hashes.
        return NotImplemented

    def __hash__(self) -> NoReturn:
        # Unhashable on purpose: a secret must not become a dict key or land in a
        # set, where it would outlive the scope that revealed it.
        raise TypeError("secrets are not hashable")

    def __len__(self) -> int:
        return len(self._value)

    def __iter__(self) -> NoReturn:
        raise TypeError("secrets are not iterable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("secrets cannot be pickled")

    def __getstate__(self) -> NoReturn:
        raise TypeError("secrets cannot be serialized")


class PlaintextPassword(PlaintextSecret):
    """A user-supplied password before hashing."""


class PlaintextToken(PlaintextSecret):
    """A raw verification or reset token, live only until it is hashed or sent."""
