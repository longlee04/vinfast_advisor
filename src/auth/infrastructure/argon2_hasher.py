"""Argon2id password hasher.

Implements the `PasswordHasher` port with the parameters frozen in
`src.auth.contracts`. Verification never raises: a wrong password and a corrupted
stored hash both return `False`, so one bad row cannot turn a failed login into a
500 that discloses it.
"""

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from src.auth.contracts import (
    ARGON2_MEMORY_COST_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    PASSWORD_MAX_BYTES,
)
from src.auth.domain.values import PasswordHash, PlaintextPassword


class Argon2idHasher:
    """Production password hasher.

    `time_cost`, `memory_cost` and `parallelism` are injectable so tests can run
    at a low cost. Only the cost changes; the algorithm never does.
    """

    def __init__(
        self,
        *,
        time_cost: int = ARGON2_TIME_COST,
        memory_cost: int = ARGON2_MEMORY_COST_KIB,
        parallelism: int = ARGON2_PARALLELISM,
    ) -> None:
        self._hasher = Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
        )
        self._dummy_hash = self.hash(PlaintextPassword("dummy-password"))

    def hash(self, password: PlaintextPassword) -> PasswordHash:
        raw = password.reveal()
        # Bound the input before it reaches the native library. Argon2 itself has
        # no practical length limit, but an unbounded body would let a caller
        # spend arbitrary CPU inside one request.
        if len(raw.encode("utf-8")) > PASSWORD_MAX_BYTES:
            raise ValueError(f"password must be at most {PASSWORD_MAX_BYTES} bytes")
        try:
            return PasswordHash(self._hasher.hash(raw))
        except HashingError as error:
            raise RuntimeError(f"password hashing failed ({type(error).__name__})") from None

    def verify(self, password: PlaintextPassword, password_hash: PasswordHash) -> bool:
        if not password_hash:
            return False
        try:
            return self._hasher.verify(password_hash, password.reveal())
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def dummy_hash(self) -> PasswordHash:
        """Return the valid Argon2id hash used for unknown-account verification."""
        return self._dummy_hash

    def needs_rehash(self, password_hash: PasswordHash) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            # A hash we cannot parse cannot be upgraded in place; the credential
            # has to be reset instead.
            return False
