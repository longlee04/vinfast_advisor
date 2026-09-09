"""Cryptographic adapters used at the Auth composition boundary."""

import hashlib
from datetime import datetime
from secrets import token_urlsafe

import jwt
from jwt import InvalidTokenError

from src.auth.application.ports import AccessTokenIssuer, TokenFactory
from src.auth.domain.values import TokenHash, UserId


class SecureTokenFactory(TokenFactory):
    """Create opaque credentials and store only SHA-256 digests."""

    def new_secret(self) -> str:
        return token_urlsafe(48)

    def hash(self, secret: str) -> TokenHash:
        return TokenHash(hashlib.sha256(secret.encode("utf-8")).hexdigest())


class JwtAccessTokenIssuer(AccessTokenIssuer):
    """Issue and validate short-lived, audience-bound access tokens."""

    def __init__(self, *, signing_key: str, algorithm: str, issuer: str, audience: str) -> None:
        self._signing_key = signing_key
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience

    def issue(self, *, user_id: UserId, session_id: str, expires_at: datetime) -> str:
        return jwt.encode(
            {"sub": str(user_id), "sid": session_id, "exp": expires_at, "iss": self._issuer, "aud": self._audience},
            self._signing_key,
            algorithm=self._algorithm,
        )

    def validate(self, token: str, *, now: datetime) -> tuple[UserId, str] | None:
        try:
            claims = jwt.decode(
                token,
                self._signing_key,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["sub", "sid", "exp", "iss", "aud"]},
                leeway=0,
            )
        except InvalidTokenError:
            return None
        if datetime.fromtimestamp(claims["exp"], tz=now.tzinfo) <= now:
            return None
        subject = claims.get("sub")
        session_id = claims.get("sid")
        if not isinstance(subject, str) or not isinstance(session_id, str):
            return None
        return UserId(subject), session_id
