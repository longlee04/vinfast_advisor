"""Session lifecycle methods shared by every authenticated role."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from src.auth.contracts import ACCESS_TOKEN_TTL_SECONDS, REFRESH_TOKEN_TTL_SECONDS
from src.auth.domain.accounts import User, UserProfile
from src.auth.domain.authorization import Role
from src.auth.domain.clock import expires_after
from src.auth.domain.errors import (
    AuthDomainError,
    ConcurrentTokenUseError,
    RefreshTokenReplayError,
    SessionRevokedError,
)
from src.auth.domain.sessions import RefreshToken, RevocationReason
from src.auth.domain.values import FamilyId, PlaintextToken, SessionId, UserId


@dataclass(frozen=True, slots=True)
class AuthSession:
    """Credentials issued after a valid login or refresh, for any role."""

    access_token: str
    refresh_token: PlaintextToken
    user_id: UserId
    session_id: SessionId
    family_id: FamilyId
    family_expires_at: datetime


class SessionLifecycle:
    """Refresh, logout, and current-user lifecycle methods."""

    async def refresh(self, raw_token: str) -> AuthSession:
        """Atomically rotate one refresh token while preserving the family deadline."""
        now = self._clock.now()
        token_hash = self._token_factory.hash(raw_token)
        async with self._transaction.transaction() as stores:
            current = await stores.refresh_tokens.get_for_rotation(token_hash)
            if current is None:
                raise SessionRevokedError("invalid refresh credential")
            try:
                current.assert_usable(now)
            except RefreshTokenReplayError:
                await stores.refresh_tokens.revoke_family(
                    current.family_id, now=now, reason=RevocationReason.REPLAY_DETECTED
                )
                raise
            if not await stores.refresh_tokens.has_live_session(str(current.session_id), current.user_id, now=now):
                raise SessionRevokedError("refresh session is not live")
            user = await stores.users.get_by_id(current.user_id)
            if user is None:
                raise SessionRevokedError("session owner no longer exists")
            user.assert_can_start_session()
            successor_secret = self._token_factory.new_secret()
            revoked, successor = current.rotate(now, self._token_factory.hash(successor_secret))
            try:
                await stores.refresh_tokens.rotate(revoked, successor)
            except ConcurrentTokenUseError as error:
                raise RefreshTokenReplayError("refresh token use was refused") from error
            return self._session_from_refresh(successor_secret, successor, now)

    async def logout_current(self, raw_token: str) -> bool:
        """Revoke only the family containing the submitted current refresh token."""
        now = self._clock.now()
        token_hash = self._token_factory.hash(raw_token)
        async with self._transaction.transaction() as stores:
            token = await stores.refresh_tokens.get_for_rotation(token_hash)
            if token is None:
                return True
            await stores.refresh_tokens.revoke_family(token.family_id, now=now, reason=RevocationReason.LOGOUT)
        return True

    async def logout_all(self, access_token: str) -> bool:
        """Revoke every live refresh family belonging to the authenticated user."""
        identity = await self.validate_access(access_token)
        if identity is None:
            return False
        user_id, _ = identity
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            await stores.refresh_tokens.revoke_all_for_user(user_id, now=now, reason=RevocationReason.LOGOUT_ALL)
        return True

    async def validate_access(self, access_token: str) -> tuple[UserId, str] | None:
        """Validate an access credential against the injected issuer and clock."""
        return self._access_tokens.validate(access_token, now=self._clock.now())

    async def me(self, access_token: str) -> User | None:
        """Return the current active user after authoritative server-side checks."""
        identity = await self.validate_access(access_token)
        if identity is None:
            return None
        user_id, session_id = identity
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_by_id(user_id)
            if user is None:
                return None
            try:
                user.assert_can_start_session()
            except AuthDomainError:
                return None
            live_session = await stores.refresh_tokens.has_live_session(session_id, user.id, now=self._clock.now())
            return user if live_session else None

    async def get_profile(self, access_token: str) -> tuple[User, UserProfile | None] | None:
        """Return the current active user and their profile if role is customer or advisor."""
        user = await self.me(access_token)
        if user is None:
            return None
        if user.role not in (Role.CUSTOMER, Role.ADVISOR):
            return user, None
        async with self._transaction.transaction() as stores:
            profile = await stores.profiles.get(user.id)
            return user, profile

    async def update_profile(
        self,
        access_token: str,
        *,
        full_name: str | None = None,
        phone_number: str | None = None,
        address: str | None = None,
        showroom_name: str | None = None,
        avatar_url: str | None = None,
        vehicle_preference: str | None = None,
        budget_preference: str | None = None,
        seats_preference: str | None = None,
        home_charging: bool | None = None,
        title: str | None = None,
        bio: str | None = None,
    ) -> UserProfile | None:
        """Update current active user profile for customer or advisor."""
        user = await self.me(access_token)
        if user is None:
            return None
        if user.role not in (Role.CUSTOMER, Role.ADVISOR):
            return None
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            current = await stores.profiles.get(user.id)
            profile = UserProfile(
                user_id=user.id,
                full_name=full_name.strip() if full_name is not None else (current.full_name if current else None),
                phone_number=phone_number.strip()
                if phone_number is not None
                else (current.phone_number if current else None),
                address=address.strip() if address is not None else (current.address if current else None),
                showroom_name=showroom_name.strip()
                if showroom_name is not None
                else (current.showroom_name if current else None),
                avatar_url=avatar_url.strip() if avatar_url is not None else (current.avatar_url if current else None),
                vehicle_preference=vehicle_preference.strip()
                if vehicle_preference is not None
                else (current.vehicle_preference if current else None),
                budget_preference=budget_preference.strip()
                if budget_preference is not None
                else (current.budget_preference if current else None),
                seats_preference=seats_preference.strip()
                if seats_preference is not None
                else (current.seats_preference if current else None),
                home_charging=home_charging
                if home_charging is not None
                else (current.home_charging if current else None),
                title=title.strip() if title is not None else (current.title if current else None),
                bio=bio.strip() if bio is not None else (current.bio if current else None),
                created_at=current.created_at if current and current.created_at else now,
                updated_at=now,
            )
            await stores.profiles.save(profile, now=now)
            return profile

    def _new_session(self, user: User, now: datetime) -> AuthSession:
        refresh_secret = self._token_factory.new_secret()
        refresh = RefreshToken(
            token_hash=self._token_factory.hash(refresh_secret),
            session_id=SessionId(str(uuid4())),
            family_id=FamilyId(str(uuid4())),
            user_id=user.id,
            issued_at=now,
            family_expires_at=expires_after(now, REFRESH_TOKEN_TTL_SECONDS),
        )
        return self._session_from_refresh(refresh_secret, refresh, now)

    def _refresh_from_session(self, session: AuthSession, now: datetime) -> RefreshToken:
        return RefreshToken(
            token_hash=self._token_factory.hash(session.refresh_token.reveal()),
            session_id=session.session_id,
            family_id=session.family_id,
            user_id=session.user_id,
            issued_at=now,
            family_expires_at=session.family_expires_at,
        )

    def _session_from_refresh(self, refresh_secret: str, refresh: RefreshToken, now: datetime) -> AuthSession:
        return AuthSession(
            access_token=self._access_tokens.issue(
                user_id=refresh.user_id,
                session_id=str(refresh.session_id),
                expires_at=expires_after(now, ACCESS_TOKEN_TTL_SECONDS),
            ),
            refresh_token=PlaintextToken(refresh_secret),
            user_id=refresh.user_id,
            session_id=refresh.session_id,
            family_id=refresh.family_id,
            family_expires_at=refresh.family_expires_at,
        )
