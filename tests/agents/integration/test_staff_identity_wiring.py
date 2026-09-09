"""Seam danh tinh nhan su phai doc duoc vai tro that tu phien Auth.

`validate_access` tra `(user_id, session_id)` — khong phai `User`. Neu seam doc
`.role` thang tren phan tu thu hai thi moi route staff (hang doi duyet, claim,
approve) vo 500 ngay o buoc giai dependency.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.auth.domain.authorization import Role


class _StubUser:
    def __init__(self, role: Role) -> None:
        self.role = role


@pytest.mark.asyncio
async def test_staff_identity_reads_role_from_the_authenticated_user(monkeypatch) -> None:
    from src import main

    async def _identity(_request: object) -> tuple[str, str]:
        return "user-42", "session-7"

    async def _user(_request: object) -> _StubUser:
        return _StubUser(Role.ADVISOR)

    monkeypatch.setattr(main, "_auth_identity", _identity)
    monkeypatch.setattr(main, "_auth_user", _user)

    identity = await main._staff_identity_from_auth(object())

    assert identity.staff_id == "user-42"
    assert identity.role == Role.ADVISOR


@pytest.mark.asyncio
async def test_staff_identity_rejects_a_request_without_a_session(monkeypatch) -> None:
    from src import main

    async def _no_identity(_request: object) -> None:
        return None

    monkeypatch.setattr(main, "_auth_identity", _no_identity)

    with pytest.raises(HTTPException) as error:
        await main._staff_identity_from_auth(object())

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_staff_identity_rejects_a_session_whose_user_vanished(monkeypatch) -> None:
    from src import main

    async def _identity(_request: object) -> tuple[str, str]:
        return "user-42", "session-7"

    async def _no_user(_request: object) -> None:
        return None

    monkeypatch.setattr(main, "_auth_identity", _identity)
    monkeypatch.setattr(main, "_auth_user", _no_user)

    with pytest.raises(HTTPException) as error:
        await main._staff_identity_from_auth(object())

    assert error.value.status_code == 401
