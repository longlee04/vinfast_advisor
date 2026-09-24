"""SQL cho tư vấn viên tự nhận/trả khách (`services/operations/customer_ownership.py`).

"Nhận" là MỘT câu `INSERT … ON CONFLICT DO NOTHING` dựa trên unique index một phần
`uq_customer_advisor_assignments_active` (agent_0040): hai người bấm cùng lúc thì đúng
một dòng được ghi, không cần khoá tay.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.customer_ownership import STATUS_RELEASED

_TRY_CLAIM = text(
    """
    INSERT INTO customer_advisor_assignments
        (assignment_id, customer_id, advisor_id, assigned_by, reason, status, assigned_at, created_at, updated_at)
    VALUES (:id, :customer_id, :advisor_id, :via, NULL, 'ACTIVE', :now, :now, :now)
    ON CONFLICT (customer_id) WHERE status = 'ACTIVE' DO NOTHING
    RETURNING assignment_id
    """
)
_OWNER = text(
    "SELECT advisor_id FROM customer_advisor_assignments WHERE customer_id = :customer_id AND status = 'ACTIVE'"
)
_RELEASE = text(
    """
    UPDATE customer_advisor_assignments
    SET status = :released, reason = :reason, unassigned_at = :now, updated_at = :now
    WHERE customer_id = :customer_id AND status = 'ACTIVE' AND advisor_id IN :advisor_ids
    """
).bindparams(bindparam("advisor_ids", expanding=True))
#: Hoạt động tư vấn viên cuối cùng với khách = muộn nhất trong (lúc nhận khách, tin nhắn
#: ADVISOR cuối trong các phiên của khách). Khách còn phiên đang do người giữ thì không nhả.
_RELEASE_STALE = text(
    """
    UPDATE customer_advisor_assignments a
    SET status = :released, reason = :reason, unassigned_at = :now, updated_at = :now
    WHERE a.status = 'ACTIVE'
      AND a.assigned_at < :before
      AND NOT EXISTS (
          SELECT 1 FROM conversation_messages m
          JOIN conversation_sessions s ON s.session_id = m.session_id
          WHERE s.customer_id = a.customer_id AND m.role = 'ADVISOR' AND m.created_at >= :before
      )
      AND NOT EXISTS (
          SELECT 1 FROM conversation_sessions s
          WHERE s.customer_id = a.customer_id AND s.status = 'ACTIVE' AND s.ownership = 'HUMAN'
      )
    RETURNING a.customer_id
    """
)
#: Người trong hàng chờ = khách ĐÃ CÓ HỒ SƠ (đăng nhập/khai thông tin, plan §20) HOẶC đã chat,
#: chưa ai phụ trách. Khách vừa đăng ký chưa chat vẫn hiện — có SĐT là gọi được.
_POOL = text(
    """
    WITH people AS (
        SELECT customer_id FROM conversation_sessions WHERE customer_id NOT LIKE 'anon-%'
        UNION
        SELECT customer_id FROM customer_profiles WHERE customer_id NOT LIKE 'anon-%'
    )
    SELECT p.customer_id, cp.display_name, cp.phone, cp.email,
           COALESCE(st.sessions_count, 0) AS sessions_count, COALESCE(st.last_seen_at, cp.updated_at) AS last_seen_at,
           COALESCE(st.waiting, FALSE) AS waiting,
           o.heat_band, o.heat_score, o.stage, o.slots_snapshot
    FROM people p
    LEFT JOIN customer_profiles cp ON cp.customer_id = p.customer_id
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS sessions_count, MAX(s.last_activity_at) AS last_seen_at,
               BOOL_OR(s.status = 'ACTIVE' AND s.ownership = 'PENDING_HANDOFF') AS waiting
        FROM conversation_sessions s WHERE s.customer_id = p.customer_id
    ) st ON TRUE
    LEFT JOIN LATERAL (
        SELECT heat_band, heat_score, stage, slots_snapshot FROM customer_opportunities
        WHERE customer_id = p.customer_id AND status IN ('OPEN', 'DORMANT')
        ORDER BY heat_score DESC LIMIT 1
    ) o ON TRUE
    WHERE NOT EXISTS (
        SELECT 1 FROM customer_advisor_assignments a WHERE a.customer_id = p.customer_id AND a.status = 'ACTIVE'
    )
    ORDER BY COALESCE(st.waiting, FALSE) DESC, o.heat_score DESC NULLS LAST,
             COALESCE(st.last_seen_at, cp.updated_at) DESC NULLS LAST
    LIMIT :limit
    """
)
_CUSTOMER_OF_SESSION = text(
    "SELECT customer_id FROM conversation_sessions WHERE session_id = CAST(:session_id AS uuid)"
)


class SqlAlchemyCustomerOwnershipRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        # Ghi đi qua ranh giới transaction chung (chỉ `unit_of_work.py` gọi `begin()`).
        self._unit_of_work: AgentUnitOfWork[AsyncSession] = AgentUnitOfWork(session_factory, lambda session: session)

    async def try_claim(self, customer_id: str, advisor_id: str, via: str, now: datetime) -> tuple[bool, str | None]:
        async with self._unit_of_work.transaction() as session:
            inserted = (
                await session.execute(
                    _TRY_CLAIM,
                    {"id": uuid4(), "customer_id": customer_id, "advisor_id": advisor_id, "via": via, "now": now},
                )
            ).first()
            owner = (await session.execute(_OWNER, {"customer_id": customer_id})).scalar()
        return inserted is not None, owner

    async def release(self, customer_id: str, advisor_ids: Sequence[str], reason: str, now: datetime) -> bool:
        async with self._unit_of_work.transaction() as session:
            result = await session.execute(
                _RELEASE,
                {
                    "customer_id": customer_id,
                    "advisor_ids": list(advisor_ids) or ["__none__"],
                    "released": STATUS_RELEASED,
                    "reason": reason,
                    "now": now,
                },
            )
        return (result.rowcount or 0) > 0

    async def release_stale(self, before: datetime, reason: str, now: datetime) -> list[str]:
        async with self._unit_of_work.transaction() as session:
            rows = await session.execute(
                _RELEASE_STALE, {"before": before, "released": STATUS_RELEASED, "reason": reason, "now": now}
            )
            return [str(row[0]) for row in rows]

    async def pool(self, limit: int) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            rows = (await session.execute(_POOL, {"limit": limit})).mappings().all()
        return [
            {
                "customer_id": row["customer_id"],
                "display_name": row["display_name"],
                "phone": row["phone"],
                "email": row["email"],
                "sessions_count": int(row["sessions_count"]),
                "last_seen_at": row["last_seen_at"],
                "waiting": bool(row["waiting"]),
                "heat_band": row["heat_band"],
                "heat_score": int(row["heat_score"]) if row["heat_score"] is not None else None,
                "stage": row["stage"],
                "slots": {
                    key: value for key, value in (row["slots_snapshot"] or {}).items() if key != "purpose_bucket"
                },
            }
            for row in rows
        ]

    async def customer_of_session(self, session_id: str) -> str | None:
        async with self._session_factory() as session:
            return (await session.execute(_CUSTOMER_OF_SESSION, {"session_id": session_id})).scalar()


__all__ = ["SqlAlchemyCustomerOwnershipRepository"]
