"""Frozen Auth credential and cookie contracts.

These values are the authoritative contract from the approved work plan. They
are deliberately module constants rather than environment variables: the
`__Host-`/`__Secure-` cookie prefixes and the token lifetimes are security
properties, not deployment tuning knobs. Changing any value here is a public
contract change and requires updating the plan first (`AGENTS.md:85`).
"""

from typing import Final

# ---- Token lifetimes (seconds) ----
ACCESS_TOKEN_TTL_SECONDS: Final[int] = 15 * 60
REFRESH_TOKEN_TTL_SECONDS: Final[int] = 30 * 24 * 60 * 60
EMAIL_VERIFICATION_TTL_SECONDS: Final[int] = 24 * 60 * 60
PASSWORD_RESET_TTL_SECONDS: Final[int] = 60 * 60
TEMPORARY_PASSWORD_TTL_SECONDS: Final[int] = 24 * 60 * 60

# ---- Cookie names ----
ACCESS_COOKIE_NAME: Final[str] = "__Host-p150_access"
REFRESH_COOKIE_NAME: Final[str] = "__Secure-p150_refresh"
CSRF_COOKIE_NAME: Final[str] = "__Host-p150_csrf"

# ---- Cookie attributes ----
ACCESS_COOKIE_PATH: Final[str] = "/"
REFRESH_COOKIE_PATH: Final[str] = "/api/v1/auth"
CSRF_COOKIE_PATH: Final[str] = "/"
COOKIE_SAMESITE: Final[str] = "lax"

CSRF_HEADER_NAME: Final[str] = "X-CSRF-Token"

# ---- Google OAuth state cookie ----
# Chỉ sống một vòng chuyển hướng sang Google và quay lại; `__Host-` buộc
# Secure + Path=/ + không Domain, đúng như các cookie phiên khác.
OAUTH_STATE_COOKIE_NAME: Final[str] = "__Host-p150_oauth_state"
OAUTH_STATE_TTL_SECONDS: Final[int] = 10 * 60

# ---- Argon2id parameters ----
ARGON2_MEMORY_COST_KIB: Final[int] = 65536
ARGON2_TIME_COST: Final[int] = 3
ARGON2_PARALLELISM: Final[int] = 4

# ---- Password policy bounds ----
PASSWORD_MIN_LENGTH: Final[int] = 12
PASSWORD_MAX_BYTES: Final[int] = 1024

# ---- Cookie prefix rules (RFC 6265bis) ----
HOST_PREFIX: Final[str] = "__Host-"
SECURE_PREFIX: Final[str] = "__Secure-"
