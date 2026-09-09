"""Administrative staff lifecycle use cases."""

from uuid import uuid4

from src.auth.application.contracts import UserPage
from src.auth.application.ports import (
    AbuseLimitExceededError,
    AccessTokenIssuer,
    AuthTransaction,
    EmailSender,
    RateLimitKeyBuilder,
    RecoveryRateLimiter,
    TokenFactory,
)
from src.auth.application.session_lifecycle import AuthSession, SessionLifecycle
from src.auth.contracts import TEMPORARY_PASSWORD_TTL_SECONDS
from src.auth.domain.accounts import AccountState, User, initial_staff_state
from src.auth.domain.authorization import Action, Role, assert_not_last_active_admin, authorize
from src.auth.domain.clock import Clock, expires_after
from src.auth.domain.errors import AuthDomainError, AuthorizationError, TemporaryPasswordRequiredError
from src.auth.domain.hashing import PasswordHasher
from src.auth.domain.passwords import validate_password
from src.auth.domain.sessions import RevocationReason
from src.auth.domain.values import NormalizedEmail, PlaintextPassword, UserId


class StaffAuthService(SessionLifecycle):
    """Creates and administers staff accounts through explicit policy checks."""

    MAX_PAGE_SIZE = 100
    DEFAULT_PAGE_SIZE = 20

    def __init__(
        self,
        transaction: AuthTransaction,
        clock: Clock,
        password_hasher: PasswordHasher,
        token_factory: TokenFactory,
        email_sender: EmailSender,
        *,
        access_tokens: AccessTokenIssuer | None = None,
        login_limiter: RecoveryRateLimiter | None = None,
        rate_limit_keys: RateLimitKeyBuilder | None = None,
    ) -> None:
        self._transaction = transaction
        self._clock = clock
        self._password_hasher = password_hasher
        self._token_factory = token_factory
        self._email_sender = email_sender
        self._access_tokens = access_tokens
        self._login_limiter = login_limiter
        self._rate_limit_keys = rate_limit_keys

    async def list_users(
        self,
        actor_id: UserId,
        *,
        role: Role | None = None,
        state: AccountState | None = None,
        email_query: str | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> UserPage:
        """Return one page of accounts for an administrator."""
        bounded_page = max(1, page)
        bounded_size = min(max(1, page_size), self.MAX_PAGE_SIZE)
        async with self._transaction.transaction() as stores:
            actor = await stores.users.get_by_id(actor_id)
            if actor is None:
                raise AuthorizationError("actor may not list users")
            authorize(actor.role, Action.LIST_USERS)
            return await stores.users.list_page(
                role=role,
                state=state,
                email_query=email_query,
                page=bounded_page,
                page_size=bounded_size,
            )

    async def login(self, raw_email: str, raw_password: str) -> AuthSession | None:
        """Authenticate staff without creating an account-existence oracle."""
        if self._access_tokens is None or self._login_limiter is None or self._rate_limit_keys is None:
            raise RuntimeError("StaffAuthService was constructed without login dependencies")
        password = PlaintextPassword(raw_password)
        try:
            email = NormalizedEmail.parse(raw_email)
        except AuthDomainError:
            self._password_hasher.verify(password, self._password_hasher.dummy_hash())
            return None
        now = self._clock.now()
        key = self._rate_limit_keys.build("staff_login", str(email))
        if not await self._login_limiter.allow(key, now=now):
            raise AbuseLimitExceededError
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_by_email(email)
            if user is None:
                self._password_hasher.verify(password, self._password_hasher.dummy_hash())
                return None
            if not self._password_hasher.verify(password, user.password_hash):
                return None
            if user.role is Role.CUSTOMER:
                return None
            try:
                user.assert_can_start_session()
            except TemporaryPasswordRequiredError:
                raise
            except AuthDomainError:
                return None
            session = self._new_session(user, now)
            await stores.refresh_tokens.add(self._refresh_from_session(session, now))
            await stores.security_events.append(event_type="staff_logged_in", occurred_at=now, actor_user_id=user.id)
            return session

    async def identify_for_password_setup(self, raw_email: str, raw_temporary_password: str) -> UserId | None:
        """Resolve a staff identity from an unexpired temporary credential."""
        if self._login_limiter is None or self._rate_limit_keys is None:
            raise RuntimeError("StaffAuthService was constructed without login dependencies")
        password = PlaintextPassword(raw_temporary_password)
        try:
            email = NormalizedEmail.parse(raw_email)
        except AuthDomainError:
            self._password_hasher.verify(password, self._password_hasher.dummy_hash())
            return None
        now = self._clock.now()
        key = self._rate_limit_keys.build("staff_login", str(email))
        if not await self._login_limiter.allow(key, now=now):
            raise AbuseLimitExceededError
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_by_email(email)
            if user is None:
                self._password_hasher.verify(password, self._password_hasher.dummy_hash())
                return None
            if user.role is Role.CUSTOMER or user.state is not AccountState.TEMPORARY_PASSWORD:
                return None
            if user.temporary_password_expires_at is not None and user.temporary_password_expires_at <= now:
                return None
            if not self._password_hasher.verify(password, user.password_hash):
                return None
            return user.id

    async def login_after_password_setup(self, user_id: UserId) -> AuthSession | None:
        """Issue a session after temporary-password completion without a second limiter hit."""
        if self._access_tokens is None:
            raise RuntimeError("StaffAuthService was constructed without login dependencies")
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_by_id(user_id)
            if user is None:
                return None
            try:
                user.assert_can_start_session()
            except AuthDomainError:
                return None
            session = self._new_session(user, now)
            await stores.refresh_tokens.add(self._refresh_from_session(session, now))
            await stores.security_events.append(event_type="staff_logged_in", occurred_at=now, actor_user_id=user.id)
            return session

    async def bootstrap_first_admin(self, raw_email: str, raw_password: str) -> bool:
        """Atomically create the first active Admin, or report that one already exists."""
        password = PlaintextPassword(raw_password)
        validate_password(password)
        now = self._clock.now()
        user = User(
            id=UserId(str(uuid4())),
            email=NormalizedEmail.parse(raw_email),
            role=Role.ADMIN,
            state=AccountState.ACTIVE,
            password_hash=self._password_hasher.hash(password),
            created_at=now,
        )
        async with self._transaction.transaction() as stores:
            claimed = await stores.users.claim_first_admin(user, now=now)
            if claimed:
                await stores.security_events.append(
                    event_type="first_admin_bootstrapped", occurred_at=now, actor_user_id=user.id
                )
            return claimed

    async def create_staff(self, actor_id: UserId, raw_email: str, role: Role) -> User:
        """Create an Advisor or Admin with a one-time temporary password delivery."""
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            actor = await stores.users.get_by_id(actor_id)
            if actor is None:
                raise AuthorizationError("actor may not create staff")
            authorize(actor.role, _creation_action(role))
            temporary_password = PlaintextPassword(self._token_factory.new_secret())
            validate_password(temporary_password)
            user = User(
                id=UserId(str(uuid4())),
                email=NormalizedEmail.parse(raw_email),
                role=role,
                state=initial_staff_state(),
                password_hash=self._password_hasher.hash(temporary_password),
                created_at=now,
                temporary_password_expires_at=expires_after(now, TEMPORARY_PASSWORD_TTL_SECONDS),
            )
            await stores.users.add(user, now=now)
            await self._email_sender.send_temporary_password(recipient=user.email, password=temporary_password)
            await stores.security_events.append(event_type="staff_created", occurred_at=now, actor_user_id=actor.id)
            return user

    async def complete_temporary_password_change(self, user_id: UserId, raw_password: str) -> User:
        """Activate a staff account after it replaces its temporary password."""
        password = PlaintextPassword(raw_password)
        validate_password(password)
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_for_update(user_id)
            if user is None:
                raise AuthorizationError("account may not change its password")
            activated = user.complete_temporary_password_change(self._password_hasher.hash(password), now)
            await stores.users.save(activated, now=now)
            await stores.refresh_tokens.revoke_all_for_user(user.id, now=now, reason=RevocationReason.PASSWORD_CHANGED)
            await stores.security_events.append(
                event_type="temporary_password_changed", occurred_at=now, actor_user_id=user.id
            )
            return activated

    async def disable_user(self, actor_id: UserId, target_id: UserId) -> User:
        """Disable an account and revoke every one of its live sessions."""
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            actor = await stores.users.get_by_id(actor_id)
            target = await stores.users.get_for_update(target_id)
            if actor is None or target is None:
                raise AuthorizationError("actor may not disable this account")
            authorize(actor.role, Action.DISABLE_USER, actor_id=str(actor.id), target_id=str(target.id))
            if target.role is Role.ADMIN and target.is_active:
                active_admins = await stores.users.lock_active_admin_count()
                assert_not_last_active_admin(Action.DISABLE_USER, active_admins - 1)
            disabled = target.disable()
            await stores.users.save(disabled, now=now)
            await stores.refresh_tokens.revoke_all_for_user(
                target.id, now=now, reason=RevocationReason.ACCOUNT_DISABLED
            )
            await stores.security_events.append(event_type="account_disabled", occurred_at=now, actor_user_id=actor.id)
            return disabled

    async def enable_user(self, actor_id: UserId, target_id: UserId) -> User:
        """Return a disabled account to service."""
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            actor = await stores.users.get_by_id(actor_id)
            if actor is None:
                raise AuthorizationError("actor may not enable accounts")
            authorize(
                actor.role,
                Action.ENABLE_USER,
                actor_id=str(actor.id),
                target_id=str(target_id),
            )
            target = await stores.users.get_for_update(target_id)
            if target is None:
                raise AuthorizationError("account may not be enabled")
            enabled = target.enable()
            await stores.users.save(enabled, now=now)
            await stores.security_events.append(event_type="user_enabled", occurred_at=now, actor_user_id=actor.id)
            return enabled

    async def activate_user(self, actor_id: UserId, target_id: UserId) -> User:
        """Activate or confirm a pending account by an administrator."""
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            actor = await stores.users.get_by_id(actor_id)
            if actor is None:
                raise AuthorizationError("actor may not activate accounts")
            authorize(
                actor.role,
                Action.ENABLE_USER,
                actor_id=str(actor.id),
                target_id=str(target_id),
            )
            target = await stores.users.get_for_update(target_id)
            if target is None:
                raise AuthorizationError("account may not be activated")
            if target.state is AccountState.PENDING_VERIFICATION:
                activated = target.verify_email()
            elif target.state is AccountState.DISABLED:
                activated = target.enable()
            elif target.state is AccountState.TEMPORARY_PASSWORD:
                from dataclasses import replace

                activated = replace(target, state=AccountState.ACTIVE)
            else:
                activated = target
            await stores.users.save(activated, now=now)
            await stores.security_events.append(event_type="user_activated", occurred_at=now, actor_user_id=actor.id)
            return activated

    async def change_role(self, actor_id: UserId, target_id: UserId, role: Role) -> User:
        """Change a staff role and invalidate sessions authorized under its old role."""
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            actor = await stores.users.get_by_id(actor_id)
            target = await stores.users.get_for_update(target_id)
            if actor is None or target is None:
                raise AuthorizationError("actor may not change this account")
            authorize(actor.role, Action.CHANGE_USER_ROLE, actor_id=str(actor.id), target_id=str(target.id))
            if target.role is Role.ADMIN and target.is_active and role is not Role.ADMIN:
                active_admins = await stores.users.lock_active_admin_count()
                assert_not_last_active_admin(Action.CHANGE_USER_ROLE, active_admins - 1)
            changed = target.change_role(role)
            await stores.users.save(changed, now=now)
            await stores.refresh_tokens.revoke_all_for_user(target.id, now=now, reason=RevocationReason.ADMIN_REVOKED)
            await stores.security_events.append(event_type="role_changed", occurred_at=now, actor_user_id=actor.id)
            return changed


def _creation_action(role: Role) -> Action:
    """Map the explicit staff role allowlist to its corresponding action."""
    match role:
        case Role.ADVISOR:
            return Action.CREATE_ADVISOR
        case Role.ADMIN:
            return Action.CREATE_ADMIN
        case Role.CUSTOMER:
            raise AuthorizationError("staff creation role is not permitted")
