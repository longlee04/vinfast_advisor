"""Pydantic request and response models for the Auth HTTP boundary."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

EmailInput = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
PasswordInput = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
TokenInput = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class AuthCredentials(BaseModel):
    """Credentials accepted by registration and login."""

    model_config = ConfigDict(extra="forbid")

    email: EmailInput
    password: PasswordInput


class EmailRequest(BaseModel):
    """Email accepted by enumeration-safe recovery endpoints."""

    model_config = ConfigDict(extra="forbid")

    email: EmailInput


class VerificationRequest(BaseModel):
    """Verification token submitted by POST."""

    model_config = ConfigDict(extra="forbid")

    token: TokenInput


class PasswordRequest(BaseModel):
    """Replacement password for authenticated password changes."""

    model_config = ConfigDict(extra="forbid")

    password: PasswordInput


class ResetPasswordRequest(BaseModel):
    """Reset token and replacement password."""

    model_config = ConfigDict(extra="forbid")

    token: TokenInput
    password: PasswordInput


class StaffPasswordSetupRequest(BaseModel):
    """Temporary credential plus replacement password."""

    model_config = ConfigDict(extra="forbid")

    email: EmailInput
    temporary_password: PasswordInput
    new_password: PasswordInput


class StaffCreateRequest(BaseModel):
    """Email and role for a new staff account; password is server-generated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    email: EmailInput
    role: Literal["advisor", "admin"]


class RoleRequest(BaseModel):
    """Target role for an administrative role change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["advisor", "admin", "customer"]


class UserSummaryResponse(BaseModel):
    """One account as shown in the administrative listing."""

    id: str
    email: str
    role: str
    state: str
    created_at: datetime
    last_activity_at: datetime | None


class UserPageResponse(BaseModel):
    """One page of the administrative listing."""

    items: list[UserSummaryResponse]
    total: int
    page: int
    page_size: int


class AuthMessage(BaseModel):
    """Stable non-sensitive Auth response."""

    message: str


class AuthError(BaseModel):
    """Stable machine-readable Auth error response."""

    error: str


class ProfileResponse(BaseModel):
    """User profile data returned to client."""

    id: str
    email: str
    role: str
    full_name: str | None = None
    phone_number: str | None = None
    address: str | None = None
    showroom_name: str | None = None
    avatar_url: str | None = None
    vehicle_preference: str | None = None
    budget_preference: str | None = None
    seats_preference: str | None = None
    home_charging: bool | None = None
    title: str | None = None
    bio: str | None = None


class UpdateProfileRequest(BaseModel):
    """Input payload to update customer/advisor profile."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    phone_number: str | None = None
    address: str | None = None
    showroom_name: str | None = None
    avatar_url: str | None = None
    vehicle_preference: str | None = None
    budget_preference: str | None = None
    seats_preference: str | None = None
    home_charging: bool | None = None
    title: str | None = None
    bio: str | None = None
