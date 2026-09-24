"""Tên/SĐT khách từ tài khoản auth (plan Customer 360, 4F).

`customer_id` của agents CHÍNH LÀ `auth_users.id` (`main._customer_id_from_auth`). Trước
đây không code nào ghi `customer_profiles`, nên màn TVV chỉ thấy UUID. Job nền của
Customer 360 lấp chỗ trống từ đây.

Chỉ ĐỌC, bằng SQL thô và có kiểm bảng tồn tại: agents không import model của auth
(ranh giới module), và DB agent có thể là DB riêng không có bảng auth — khi đó trả `None`.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.logging import get_agent_logger

logger = get_agent_logger("agent.adapters.customer_identity_source")

_LOOKUP = text("SELECT p.full_name, p.phone_number FROM auth_user_profiles p WHERE p.user_id = :customer_id")
_TABLE_EXISTS = text("SELECT to_regclass('public.auth_user_profiles') IS NOT NULL")


class AuthProfileIdentitySource:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._available: bool | None = None

    async def lookup(self, customer_id: str) -> tuple[str | None, str | None] | None:
        try:
            async with self._session_factory() as session:
                if self._available is None:
                    self._available = bool(await session.scalar(_TABLE_EXISTS))
                if not self._available:
                    return None
                row = (await session.execute(_LOOKUP, {"customer_id": customer_id})).first()
        except SQLAlchemyError:
            logger.warning("customer360.identity khong doc duoc auth_user_profiles", exc_info=True)
            return None
        return None if row is None else (row[0], row[1])


__all__ = ["AuthProfileIdentitySource"]
