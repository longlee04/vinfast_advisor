"""Value object tests: canonical identity and non-rendering secrets."""

import pickle
from typing import Any, cast

import pytest

from src.auth.domain.errors import EmailDomainNotAllowedError, InvalidEmailError
from src.auth.domain.values import (
    NormalizedEmail,
    PlaintextPassword,
    PlaintextSecret,
    PlaintextToken,
)


class TestEmailNormalization:
    def test_lowercases_local_and_domain(self) -> None:
        assert NormalizedEmail.parse("Alice.Smith@GMail.COM").value == "alice.smith@gmail.com"

    def test_trims_surrounding_whitespace(self) -> None:
        assert NormalizedEmail.parse("  bob@gmail.com \t\n").value == "bob@gmail.com"

    def test_strips_invisible_edge_characters(self) -> None:
        """A copied address can carry a zero-width space that `strip()` leaves."""
        assert NormalizedEmail.parse("​carol@gmail.com﻿").value == "carol@gmail.com"

    def test_normalization_is_idempotent(self) -> None:
        once = NormalizedEmail.parse(" Dave@Gmail.com ")
        assert NormalizedEmail.parse(once.value) == once

    def test_equal_inputs_normalize_to_equal_values(self) -> None:
        assert NormalizedEmail.parse("Eve@gmail.com") == NormalizedEmail.parse("eve@GMAIL.COM")

    def test_exposes_local_part_and_domain(self) -> None:
        email = NormalizedEmail.parse("frank@gmail.com")
        assert email.local_part == "frank"
        assert email.domain == "gmail.com"

    def test_is_hashable_for_use_as_a_key(self) -> None:
        assert len({NormalizedEmail.parse("g@gmail.com"), NormalizedEmail.parse("G@GMAIL.COM")}) == 1


class TestGmailDotsAndPlusStayDistinct:
    """Dot/plus canonicalization is deliberately NOT performed."""

    def test_dotted_local_part_is_a_distinct_identity(self) -> None:
        assert NormalizedEmail.parse("a.b@gmail.com") != NormalizedEmail.parse("ab@gmail.com")

    def test_plus_tag_is_a_distinct_identity(self) -> None:
        assert NormalizedEmail.parse("a+tag@gmail.com") != NormalizedEmail.parse("a@gmail.com")


class TestEmailRejection:
    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "no-at-sign", "two@@gmail.com", "a@b@gmail.com", "@gmail.com", "user@"],
    )
    def test_rejects_structurally_invalid_addresses(self, raw: str) -> None:
        with pytest.raises(InvalidEmailError):
            NormalizedEmail.parse(raw)

    @pytest.mark.parametrize("raw", ["user@gmailcom", "user@.gmail.com", "user@gmail.com.", "user@a..b"])
    def test_rejects_invalid_domains(self, raw: str) -> None:
        with pytest.raises(InvalidEmailError):
            NormalizedEmail.parse(raw)

    def test_rejects_interior_whitespace(self) -> None:
        with pytest.raises(InvalidEmailError):
            NormalizedEmail.parse("first last@gmail.com")

    def test_rejects_interior_control_character(self) -> None:
        with pytest.raises(InvalidEmailError):
            NormalizedEmail.parse("user\x00@gmail.com")

    def test_rejects_address_over_254_characters(self) -> None:
        with pytest.raises(InvalidEmailError):
            NormalizedEmail.parse("a" * 60 + "@" + "b" * 200 + ".com")

    def test_rejects_local_part_over_64_characters(self) -> None:
        with pytest.raises(InvalidEmailError):
            NormalizedEmail.parse("a" * 65 + "@gmail.com")

    def test_rejects_non_string_input(self) -> None:
        with pytest.raises(InvalidEmailError):
            NormalizedEmail.parse(cast(str, None))


class TestCustomerEmailDomain:
    @pytest.mark.parametrize("raw", ["Helen@Gmail.com", "Helen@Outlook.com", "Helen@Yahoo.com", "Helen@iCloud.com"])
    def test_accepts_common_mail_providers(self, raw: str) -> None:
        assert NormalizedEmail.parse_customer(raw).value == raw.lower()

    @pytest.mark.parametrize("raw", ["user@googlemail.com", "user@gmail.com.evil.co", "user@10minutemail.com"])
    def test_rejects_domains_outside_allowlist(self, raw: str) -> None:
        with pytest.raises(EmailDomainNotAllowedError):
            NormalizedEmail.parse_customer(raw)

    def test_deployment_can_narrow_the_allowlist(self) -> None:
        """`AUTH_CUSTOMER_EMAIL_DOMAINS` reaches here as `allowed_domains`."""
        only_gmail = frozenset({"gmail.com"})
        assert NormalizedEmail.parse_customer("helen@gmail.com", allowed_domains=only_gmail).domain == "gmail.com"
        with pytest.raises(EmailDomainNotAllowedError):
            NormalizedEmail.parse_customer("helen@outlook.com", allowed_domains=only_gmail)

    def test_empty_allowlist_falls_back_to_defaults(self) -> None:
        """A mistyped env var must not silently open registration to every domain."""
        with pytest.raises(EmailDomainNotAllowedError):
            NormalizedEmail.parse_customer("user@10minutemail.com", allowed_domains=frozenset())

    def test_staff_parse_still_allows_any_domain(self) -> None:
        """Only customer registration is allowlisted; staff are created by Admin."""
        assert NormalizedEmail.parse("advisor@p150.test").domain == "p150.test"


class TestSecretsDoNotRender:
    SECRET = "s3cr3t-p4ssw0rd!"

    @pytest.mark.parametrize("wrapper", [PlaintextSecret, PlaintextPassword, PlaintextToken])
    def test_repr_redacts(self, wrapper: type[PlaintextSecret]) -> None:
        assert self.SECRET not in repr(wrapper(self.SECRET))

    @pytest.mark.parametrize("wrapper", [PlaintextSecret, PlaintextPassword, PlaintextToken])
    def test_str_redacts(self, wrapper: type[PlaintextSecret]) -> None:
        assert self.SECRET not in str(wrapper(self.SECRET))

    def test_fstring_interpolation_redacts(self) -> None:
        assert self.SECRET not in f"{PlaintextPassword(self.SECRET)}"

    def test_format_redacts(self) -> None:
        assert self.SECRET not in f"{PlaintextPassword(self.SECRET)}"

    def test_exception_message_containing_a_secret_redacts(self) -> None:
        """A secret passed into an error message must not leak through it."""
        error = ValueError(f"bad credential: {PlaintextPassword(self.SECRET)}")
        assert self.SECRET not in str(error)

    def test_reveal_returns_the_plaintext(self) -> None:
        assert PlaintextPassword(self.SECRET).reveal() == self.SECRET

    def test_length_is_available_without_revealing(self) -> None:
        assert len(PlaintextPassword(self.SECRET)) == len(self.SECRET)

    def test_cannot_be_pickled(self) -> None:
        with pytest.raises(TypeError):
            pickle.dumps(PlaintextPassword(self.SECRET))

    def test_cannot_be_iterated(self) -> None:
        with pytest.raises(TypeError):
            list(cast(Any, PlaintextPassword(self.SECRET)))

    def test_is_not_hashable(self) -> None:
        with pytest.raises(TypeError):
            {cast(Any, PlaintextPassword(self.SECRET))}

    def test_equality_is_not_supported(self) -> None:
        """Plaintext comparison is not part of any flow; hashes are compared."""
        assert (PlaintextPassword(self.SECRET) == PlaintextPassword(self.SECRET)) is False

    def test_rejects_non_string_value(self) -> None:
        with pytest.raises(TypeError):
            PlaintextPassword(cast(str, 12345))
