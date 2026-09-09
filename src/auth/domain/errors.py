"""Typed Auth domain errors.

Every rejection carries a stable machine-readable `code`. Presentation maps
codes to HTTP responses (Todo 7); the domain never formats an HTTP status or a
user-facing sentence, and never embeds a credential in a message
(`AGENTS.md:43`).

Enumeration safety is a presentation concern, not a domain one: the domain says
precisely what went wrong so the application layer can decide what is safe to
disclose.
"""


class AuthDomainError(Exception):
    """Base class for every Auth domain rule violation."""

    code = "auth_domain_error"


class InvalidEmailError(AuthDomainError):
    code = "invalid_email"


class EmailDomainNotAllowedError(InvalidEmailError):
    code = "email_domain_not_allowed"


class PasswordPolicyError(AuthDomainError):
    code = "password_policy_violation"


class PasswordTooShortError(PasswordPolicyError):
    code = "password_too_short"


class PasswordTooLongError(PasswordPolicyError):
    code = "password_too_long"


class PasswordMissingCharacterClassError(PasswordPolicyError):
    code = "password_missing_character_class"


class PasswordContainsControlCharacterError(PasswordPolicyError):
    code = "password_contains_control_character"


class AuthorizationError(AuthDomainError):
    code = "not_authorized"


class AccountStateError(AuthDomainError):
    code = "invalid_account_state"


class AccountNotVerifiedError(AccountStateError):
    code = "account_not_verified"


class AccountDisabledError(AccountStateError):
    code = "account_disabled"


class TemporaryPasswordRequiredError(AccountStateError):
    code = "temporary_password_required"


class TemporaryPasswordExpiredError(AccountStateError):
    code = "temporary_password_expired"


class TokenError(AuthDomainError):
    code = "invalid_token"


class TokenExpiredError(TokenError):
    code = "token_expired"


class TokenAlreadyConsumedError(TokenError):
    code = "token_already_consumed"


class TokenPurposeMismatchError(TokenError):
    code = "token_purpose_mismatch"


class SessionError(AuthDomainError):
    code = "invalid_session"


class SessionRevokedError(SessionError):
    code = "session_revoked"


class SessionExpiredError(SessionError):
    code = "session_expired"


class RefreshTokenReplayError(SessionError):
    code = "refresh_token_replay"


class ConcurrentTokenUseError(SessionError):
    """A repository CAS refused a simultaneous token operation."""

    code = "concurrent_token_use"


class LastAdminProtectedError(AuthDomainError):
    code = "last_admin_protected"
