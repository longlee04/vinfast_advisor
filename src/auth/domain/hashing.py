"""Password hashing policy and port.

The domain owns the *policy* (which algorithm, which cost parameters, what the
verification contract is) while the concrete Argon2id adapter lives in
infrastructure. That split is what lets application code depend on hashing
without importing `argon2` (`AGENTS.md:27`).

Argon2id with m=64MiB, t=3, p=4 is the OWASP-recommended baseline. It is chosen
over bcrypt mainly because bcrypt silently truncates input at 72 bytes, which
would make the documented password bound a lie.
"""

from typing import Protocol

from src.auth.contracts import ARGON2_MEMORY_COST_KIB, ARGON2_PARALLELISM, ARGON2_TIME_COST
from src.auth.domain.values import PasswordHash, PlaintextPassword

__all__ = [
    "ARGON2_MEMORY_COST_KIB",
    "ARGON2_PARALLELISM",
    "ARGON2_TIME_COST",
    "PasswordHasher",
]


class PasswordHasher(Protocol):
    """Hashes and verifies passwords.

    Implementations must never raise on a wrong password or a malformed stored
    hash: both are ordinary outcomes and must be reported as `False`, so a
    corrupted row cannot turn a failed login into a 500 that reveals it.
    """

    def hash(self, password: PlaintextPassword) -> PasswordHash:
        """Return a self-describing hash that encodes its own parameters."""
        ...

    def verify(self, password: PlaintextPassword, password_hash: PasswordHash) -> bool:
        """Return whether `password` matches `password_hash`."""
        ...

    def dummy_hash(self) -> PasswordHash:
        """Return a valid non-account hash for enumeration-safe verification."""
        ...

    def needs_rehash(self, password_hash: PasswordHash) -> bool:
        """Return whether the hash was produced with outdated parameters.

        Only meaningful after a *successful* verification: rehashing on a failed
        attempt would mean rehashing on attacker-supplied input.
        """
        ...
