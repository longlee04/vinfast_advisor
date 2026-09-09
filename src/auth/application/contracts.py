"""Application contracts for administrative Auth use cases."""

from dataclasses import dataclass
from datetime import datetime

from src.auth.domain.accounts import AccountState
from src.auth.domain.authorization import Role
from src.auth.domain.values import NormalizedEmail, UserId


@dataclass(frozen=True, slots=True)
class UserSummary:
    """One row of the administrative user listing."""

    id: UserId
    email: NormalizedEmail
    role: Role
    state: AccountState
    created_at: datetime
    last_activity_at: datetime | None


@dataclass(frozen=True, slots=True)
class UserPage:
    """One page of the administrative user listing."""

    items: tuple[UserSummary, ...]
    total: int
    page: int
    page_size: int
