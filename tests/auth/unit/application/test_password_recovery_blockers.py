"""Task 6 review-blocker regressions for password recovery."""

import pytest

from src.auth.domain.values import PlaintextToken
from tests.auth.unit.application.password_recovery_fakes import (
    NEW_PASSWORD,
    NOW,
    build_service,
    make_user,
)


@pytest.mark.asyncio
async def test_reset_rate_limit_buckets_distinct_invalid_tokens_by_user() -> None:
    service, stores, _, _, _, _, limiter = build_service()
    user = make_user()
    await stores.save(user, now=NOW)

    await service.reset_password("invalid-one", NEW_PASSWORD)
    await service.reset_password("invalid-two", NEW_PASSWORD)

    assert len(limiter.keys) == 2
    assert limiter.keys[0] != limiter.keys[1]


@pytest.mark.asyncio
async def test_password_recovery_sends_a_typed_plaintext_token() -> None:
    service, stores, _, _, email, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)

    await service.forgot_password(str(user.email))

    assert isinstance(email.deliveries[0][1], PlaintextToken)


@pytest.mark.asyncio
async def test_6_15_declared_email_delivery_error_rolls_back_before_generic_response() -> None:
    service, stores, _, _, email, _, _ = build_service()
    user = make_user()
    await stores.save(user, now=NOW)
    email.fail_delivery = True

    assert await service.forgot_password(str(user.email)) is True
    assert not stores.one_time
