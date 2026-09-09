"""Task 6 password recovery application acceptance tests."""

from datetime import timedelta

import anyio
import pytest

from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.clock import FixedClock
from src.auth.domain.errors import PasswordTooShortError
from src.auth.domain.sessions import OneTimeToken, RefreshToken, RevocationReason, TokenPurpose
from src.auth.domain.values import FamilyId, SessionId, TokenHash
from tests.auth.unit.application.password_recovery_fakes import (
    NEW_PASSWORD,
    NOW,
    build_service,
    make_user,
)


@pytest.mark.asyncio
async def test_6_1_known_and_unknown_forgot_requests_return_equivalent_output() -> None:
    service, stores, _, hasher, _, _, _ = build_service()
    await stores.save(make_user(), now=NOW)

    known = await service.forgot_password("customer@gmail.com")
    unknown = await service.forgot_password("unknown@gmail.com")

    assert known == unknown is True
    assert hasher.verify_calls == 1


@pytest.mark.asyncio
async def test_6_2_reset_accepts_token_before_one_hour_expiry() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    await service.forgot_password(str(user.email))

    assert await service.reset_password(tokens.secrets[-1], NEW_PASSWORD) is True


@pytest.mark.asyncio
async def test_6_3_reset_rejects_token_at_one_hour_expiry() -> None:
    service, stores, _, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    token = OneTimeToken(TokenHash("hash:expired"), TokenPurpose.PASSWORD_RESET, user.id, NOW, NOW + timedelta(hours=1))
    stores.one_time[token.token_hash] = token
    service._clock = FixedClock(NOW + timedelta(hours=1))

    assert await service.reset_password("expired", NEW_PASSWORD) is False


@pytest.mark.asyncio
async def test_6_4_new_reset_token_rejects_the_old_token() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    await service.forgot_password(str(user.email))
    old_token = tokens.secrets[-1]
    await service.forgot_password(str(user.email))

    assert await service.reset_password(old_token, NEW_PASSWORD) is False


@pytest.mark.asyncio
async def test_6_5_consumed_reset_token_is_rejected() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    await service.forgot_password(str(user.email))
    token = tokens.secrets[-1]
    assert await service.reset_password(token, NEW_PASSWORD) is True

    assert await service.reset_password(token, NEW_PASSWORD) is False


@pytest.mark.asyncio
async def test_6_6_email_verification_token_is_rejected_as_reset_token() -> None:
    service, stores, _, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    token = OneTimeToken(
        TokenHash("hash:verify"), TokenPurpose.EMAIL_VERIFICATION, user.id, NOW, NOW + timedelta(hours=1)
    )
    stores.one_time[token.token_hash] = token

    assert await service.reset_password("verify", NEW_PASSWORD) is False


@pytest.mark.asyncio
async def test_6_7_reset_token_for_another_user_is_rejected() -> None:
    service, stores, _, _, _, _, _ = build_service()
    user, other = make_user(), make_user("other")
    await stores.save(user, now=NOW)
    token = OneTimeToken(TokenHash("hash:other"), TokenPurpose.PASSWORD_RESET, other.id, NOW, NOW + timedelta(hours=1))
    stores.one_time[token.token_hash] = token

    await stores.save(other, now=NOW)

    assert await service.reset_password("other", NEW_PASSWORD) is True


@pytest.mark.asyncio
async def test_6_8_malformed_reset_token_returns_generic_failure() -> None:
    service, stores, _, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)

    assert await service.reset_password("malformed", NEW_PASSWORD) is False


@pytest.mark.asyncio
async def test_6_9_concurrent_reset_token_use_allows_exactly_one_success() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    await service.forgot_password(str(user.email))
    stores.synchronize_consumption = True
    results: list[bool] = []

    async def reset_once() -> None:
        results.append(await service.reset_password(tokens.secrets[-1], NEW_PASSWORD))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(reset_once)
        task_group.start_soon(reset_once)

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_6_10_change_password_enforces_common_policy() -> None:
    service, stores, _, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)

    with pytest.raises(PasswordTooShortError):
        await service.change_password(user.id, "short")


@pytest.mark.asyncio
async def test_6_11_reset_password_enforces_common_policy() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    await service.forgot_password(str(user.email))

    with pytest.raises(PasswordTooShortError):
        await service.reset_password(tokens.secrets[-1], "short")


@pytest.mark.asyncio
async def test_6_12_successful_reset_revokes_every_refresh_family() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    for suffix in ("one", "two"):
        refresh = RefreshToken(
            TokenHash(f"refresh-{suffix}"),
            SessionId(f"session-{suffix}"),
            FamilyId(f"family-{suffix}"),
            user.id,
            NOW,
            NOW + timedelta(days=30),
        )
        stores.refresh_by_hash[refresh.token_hash] = refresh
    await service.forgot_password(str(user.email))

    assert await service.reset_password(tokens.secrets[-1], NEW_PASSWORD) is True
    assert all(token.is_revoked for token in stores.refresh_by_hash.values())


@pytest.mark.asyncio
async def test_6_13_pre_reset_refresh_tokens_have_password_reset_revocation_reason() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    refresh = RefreshToken(
        TokenHash("refresh"), SessionId("session"), FamilyId("family"), user.id, NOW, NOW + timedelta(days=30)
    )
    stores.refresh_by_hash[refresh.token_hash] = refresh
    await service.forgot_password(str(user.email))

    await service.reset_password(tokens.secrets[-1], NEW_PASSWORD)

    assert stores.refresh_by_hash[refresh.token_hash].revocation_reason is RevocationReason.PASSWORD_RESET


@pytest.mark.asyncio
async def test_6_14_successful_reset_does_not_create_a_session() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    await service.forgot_password(str(user.email))

    assert await service.reset_password(tokens.secrets[-1], NEW_PASSWORD) is True
    assert not stores.refresh_by_hash


@pytest.mark.asyncio
async def test_6_15_provider_failure_rolls_back_for_a_retry_without_multiple_active_tokens() -> None:
    service, stores, _, _, email, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    email.fail_delivery = True

    assert await service.forgot_password(str(user.email)) is True
    assert not stores.one_time
    email.fail_delivery = False

    assert await service.forgot_password(str(user.email)) is True
    assert len(stores.one_time) == 1
    assert len(email.deliveries) == 1


@pytest.mark.asyncio
async def test_6_16_provider_failure_is_generic_for_known_and_unknown_accounts() -> None:
    service, stores, _, _, email, _, _ = build_service()
    await stores.save(make_user(), now=NOW)
    email.fail_delivery = True

    known = await service.forgot_password("customer@gmail.com")
    unknown = await service.forgot_password("unknown@gmail.com")

    assert known == unknown is True
    assert not stores.one_time


@pytest.mark.asyncio
async def test_reset_rescues_a_staff_account_stuck_on_an_expired_temporary_password() -> None:
    service, stores, tokens, _, _, _, _ = build_service()
    advisor = make_user("advisor")
    temporary_advisor = User(
        id=advisor.id,
        email=advisor.email,
        role=Role.ADVISOR,
        state=AccountState.TEMPORARY_PASSWORD,
        password_hash=advisor.password_hash,
        created_at=NOW,
    )
    await stores.save(temporary_advisor, now=NOW)

    assert await service.forgot_password(str(temporary_advisor.email)) is True
    assert await service.reset_password(tokens.secrets[-1], NEW_PASSWORD) is True
    assert stores.users_by_id[temporary_advisor.id].state is AccountState.ACTIVE


@pytest.mark.asyncio
async def test_recovery_surfaces_rate_limit_with_hashed_identity_keys() -> None:
    service, stores, _, _, _, keys, limiter = build_service()
    user = make_user()
    await stores.save(user, now=NOW)

    await service.forgot_password(str(user.email))
    await service.reset_password("malformed", NEW_PASSWORD)

    assert [scope for scope, _ in keys.calls] == ["forgot", "reset"]
    assert all("@gmail.com" not in key for key in limiter.keys)
    assert all(key.startswith(("forgot:", "reset:")) for key in limiter.keys)
