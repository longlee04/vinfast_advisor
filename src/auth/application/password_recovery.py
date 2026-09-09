"""Password change and recovery use cases."""

from src.auth.application.ports import (
    AuthTransaction,
    EmailDeliveryError,
    EmailSender,
    RateLimitKeyBuilder,
    RecoveryRateLimiter,
    TokenFactory,
)
from src.auth.contracts import PASSWORD_RESET_TTL_SECONDS
from src.auth.domain.clock import Clock, expires_after
from src.auth.domain.errors import AuthDomainError
from src.auth.domain.hashing import PasswordHasher
from src.auth.domain.passwords import validate_password
from src.auth.domain.sessions import OneTimeToken, RevocationReason, TokenPurpose
from src.auth.domain.values import NormalizedEmail, PlaintextPassword, PlaintextToken, UserId


class PasswordRecoveryService:
    """Change passwords and issue/consume enumeration-safe reset credentials."""

    def __init__(
        self,
        transaction: AuthTransaction,
        clock: Clock,
        password_hasher: PasswordHasher,
        token_factory: TokenFactory,
        email_sender: EmailSender,
        rate_limiter: RecoveryRateLimiter,
        rate_limit_keys: RateLimitKeyBuilder,
    ) -> None:
        self._transaction = transaction
        self._clock = clock
        self._password_hasher = password_hasher
        self._token_factory = token_factory
        self._email_sender = email_sender
        self._rate_limiter = rate_limiter
        self._rate_limit_keys = rate_limit_keys

    async def change_password(self, user_id: UserId, raw_password: str) -> bool:
        """Replace an authenticated user's password and revoke every refresh family."""
        password = PlaintextPassword(raw_password)
        validate_password(password)
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_for_update(user_id)
            if user is None:
                return False
            await stores.users.save(user.change_password(self._password_hasher.hash(password)), now=now)
            await stores.refresh_tokens.revoke_all_for_user(user.id, now=now, reason=RevocationReason.PASSWORD_CHANGED)
            await stores.security_events.append(event_type="password_changed", occurred_at=now, actor_user_id=user.id)
        return True

    async def forgot_password(self, raw_email: str) -> bool:
        """Issue a reset credential without disclosing whether its account exists."""
        password = PlaintextPassword(self._token_factory.new_secret())
        try:
            email = NormalizedEmail.parse(raw_email)
        except AuthDomainError:
            self._password_hasher.verify(password, self._password_hasher.dummy_hash())
            return True
        now = self._clock.now()
        key = self._rate_limit_keys.build("forgot", str(email))
        if not await self._rate_limiter.allow(key, now=now):
            self._password_hasher.verify(password, self._password_hasher.dummy_hash())
            return True
        try:
            async with self._transaction.transaction() as stores:
                user = await stores.users.get_by_email(email)
                if user is None:
                    self._password_hasher.verify(password, self._password_hasher.dummy_hash())
                    return True
                token = PlaintextToken(self._token_factory.new_secret())
                await stores.one_time_tokens.issue(
                    OneTimeToken(
                        token_hash=self._token_factory.hash(token.reveal()),
                        purpose=TokenPurpose.PASSWORD_RESET,
                        user_id=user.id,
                        issued_at=now,
                        expires_at=expires_after(now, PASSWORD_RESET_TTL_SECONDS),
                    ),
                    now=now,
                )
                await self._email_sender.send_password_reset(recipient=user.email, token=token)
        except EmailDeliveryError:
            return True
        return True

    async def reset_password(self, raw_token: str, raw_password: str) -> bool:
        """Consume a reset credential and derive its owner inside the transaction."""
        password = PlaintextPassword(raw_password)
        validate_password(password)
        now = self._clock.now()
        token_hash = self._token_factory.hash(raw_token)
        key = self._rate_limit_keys.build("reset", str(token_hash))
        if not await self._rate_limiter.allow(key, now=now):
            return False
        try:
            async with self._transaction.transaction() as stores:
                token = await stores.one_time_tokens.get_for_consumption(token_hash)
                if token is None:
                    return False
                if token.purpose is not TokenPurpose.PASSWORD_RESET:
                    return False
                user = await stores.users.get_for_update(token.user_id)
                if user is None:
                    return False
                consumed = token.consume(now, purpose=TokenPurpose.PASSWORD_RESET, user_id=user.id)
                await stores.one_time_tokens.mark_consumed(consumed)
                await stores.users.save(user.reset_password(self._password_hasher.hash(password)), now=now)
                await stores.refresh_tokens.revoke_all_for_user(
                    user.id, now=now, reason=RevocationReason.PASSWORD_RESET
                )
                await stores.security_events.append(event_type="password_reset", occurred_at=now, actor_user_id=user.id)
        except AuthDomainError:
            return False
        return True
