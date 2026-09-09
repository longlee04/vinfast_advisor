"""Argon2id hashing tests.

Cost parameters are lowered here so the suite stays fast; the algorithm and the
verification contract are exactly the production ones. Parameter values
themselves are asserted against the frozen contract separately.
"""

import pytest

from src.auth.contracts import ARGON2_MEMORY_COST_KIB, ARGON2_PARALLELISM, ARGON2_TIME_COST
from src.auth.domain.hashing import PasswordHasher
from src.auth.domain.values import PasswordHash, PlaintextPassword
from src.auth.infrastructure.argon2_hasher import Argon2idHasher

PASSWORD = PlaintextPassword("Str0ng!Passw0rd")
OTHER = PlaintextPassword("An0ther!Passw0rd")

# Low cost keeps the suite fast. Production values are asserted in
# TestFrozenParameters below.
TEST_COST = {"time_cost": 1, "memory_cost": 8, "parallelism": 1}


@pytest.fixture
def hasher() -> Argon2idHasher:
    return Argon2idHasher(**TEST_COST)


class TestFrozenParameters:
    def test_production_defaults_match_the_contract(self) -> None:
        assert ARGON2_MEMORY_COST_KIB == 65536
        assert ARGON2_TIME_COST == 3
        assert ARGON2_PARALLELISM == 4

    def test_production_hasher_encodes_those_parameters(self) -> None:
        """The hash string carries its own parameters, so upgrades are detectable."""
        encoded = Argon2idHasher().hash(PASSWORD)
        assert "$argon2id$" in encoded
        assert "m=65536" in encoded
        assert "t=3" in encoded
        assert "p=4" in encoded


class TestHashAndVerify:
    def test_verifies_the_correct_password(self, hasher: Argon2idHasher) -> None:
        assert hasher.verify(PASSWORD, hasher.hash(PASSWORD)) is True

    def test_rejects_a_wrong_password(self, hasher: Argon2idHasher) -> None:
        assert hasher.verify(OTHER, hasher.hash(PASSWORD)) is False

    def test_hash_is_salted_so_repeats_differ(self, hasher: Argon2idHasher) -> None:
        assert hasher.hash(PASSWORD) != hasher.hash(PASSWORD)

    def test_both_salted_hashes_still_verify(self, hasher: Argon2idHasher) -> None:
        assert hasher.verify(PASSWORD, hasher.hash(PASSWORD)) is True
        assert hasher.verify(PASSWORD, hasher.hash(PASSWORD)) is True

    def test_hash_never_contains_the_plaintext(self, hasher: Argon2idHasher) -> None:
        assert "Str0ng!Passw0rd" not in hasher.hash(PASSWORD)

    def test_uses_argon2id_variant(self, hasher: Argon2idHasher) -> None:
        assert hasher.hash(PASSWORD).startswith("$argon2id$")

    def test_verification_is_case_sensitive(self, hasher: Argon2idHasher) -> None:
        assert hasher.verify(PlaintextPassword("str0ng!passw0rd"), hasher.hash(PASSWORD)) is False

    def test_unicode_password_round_trips(self, hasher: Argon2idHasher) -> None:
        secret = PlaintextPassword("Mật Khẩu Số1!")
        assert hasher.verify(secret, hasher.hash(secret)) is True


class TestMalformedHashesNeverRaise:
    """A corrupted stored hash is a failed login, not a 500 that discloses it."""

    @pytest.mark.parametrize(
        "stored",
        ["", "not-a-hash", "$argon2id$broken", "$2b$12$abcdefghijklmnopqrstuv", "$argon2id$v=19$m=8"],
    )
    def test_returns_false_instead_of_raising(self, hasher: Argon2idHasher, stored: str) -> None:
        assert hasher.verify(PASSWORD, PasswordHash(stored)) is False

    def test_empty_stored_hash_returns_false(self, hasher: Argon2idHasher) -> None:
        assert hasher.verify(PASSWORD, PasswordHash("")) is False

    def test_needs_rehash_on_malformed_hash_returns_false(self, hasher: Argon2idHasher) -> None:
        assert hasher.needs_rehash(PasswordHash("not-a-hash")) is False


class TestDummyHash:
    def test_dummy_hash_is_valid_argon2id_and_rejects_a_password(self) -> None:
        hasher = Argon2idHasher(time_cost=1, memory_cost=8, parallelism=1)

        assert hasher.dummy_hash().startswith("$argon2id$")
        assert hasher.verify(PlaintextPassword("not-the-dummy"), hasher.dummy_hash()) is False


class TestNeedsRehash:
    def test_current_parameters_do_not_need_rehash(self, hasher: Argon2idHasher) -> None:
        assert hasher.needs_rehash(hasher.hash(PASSWORD)) is False

    def test_outdated_parameters_need_rehash(self) -> None:
        weak = Argon2idHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
        stronger = Argon2idHasher(time_cost=2, memory_cost=16, parallelism=1)
        assert stronger.needs_rehash(weak) is True

    def test_old_hash_still_verifies_before_upgrade(self) -> None:
        """Raising the cost must not lock out existing users."""
        weak = Argon2idHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
        stronger = Argon2idHasher(time_cost=2, memory_cost=16, parallelism=1)
        assert stronger.verify(PASSWORD, weak) is True

    def test_rehash_decision_is_independent_of_verification(self, hasher: Argon2idHasher) -> None:
        """needs_rehash is only meaningful after a *successful* verification."""
        stored = hasher.hash(PASSWORD)
        assert hasher.verify(OTHER, stored) is False
        assert hasher.needs_rehash(stored) is False


class TestInputBounds:
    def test_rejects_input_above_the_byte_ceiling(self, hasher: Argon2idHasher) -> None:
        with pytest.raises(ValueError):
            hasher.hash(PlaintextPassword("a" * 2000))

    def test_accepts_input_at_the_ceiling(self, hasher: Argon2idHasher) -> None:
        hasher.hash(PlaintextPassword("a" * 1024))


class TestPortConformance:
    def test_adapter_satisfies_the_domain_port(self, hasher: Argon2idHasher) -> None:
        port: PasswordHasher = hasher
        assert port.verify(PASSWORD, port.hash(PASSWORD)) is True

    def test_domain_port_does_not_import_argon2(self) -> None:
        """Application code depends on the port, never on the library."""
        import src.auth.domain.hashing as module

        assert "argon2" not in [name.split(".")[0] for name in vars(module) if not name.startswith("_")]
