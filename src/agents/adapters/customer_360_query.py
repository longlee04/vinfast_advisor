"""Đọc cho màn Customer 360 — hồ sơ ĐÚNG 3 câu SQL (plan §5.6), danh sách cơ hội, picker, số liệu admin.

SQL viết tay (`text`) vì cả ba câu hồ sơ là JOIN/LATERAL/VIEW đọc một lần; dịch sang ORM
chỉ làm khó đọc mà không thêm an toàn nào. Mọi tham số đều bind, không nối chuỗi.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.domain.customer_overview import FactRow, HeaderRow, OpportunityRow, SessionRowIn

_HEADER_AND_OPPORTUNITIES = text(
    """
    SELECT c.customer_id, cp.display_name, cp.phone, cp.address, a.advisor_id,
           o.opportunity_id, o.vehicle_type, o.buyer_for, o.status, o.stage, o.heat_score, o.heat_band,
           o.heat_breakdown, o.slots_snapshot, o.slot_history, o.last_seen_at
    FROM (SELECT CAST(:customer_id AS varchar) AS customer_id) c
    LEFT JOIN customer_profiles cp ON cp.customer_id = c.customer_id
    LEFT JOIN LATERAL (
        SELECT advisor_id FROM customer_advisor_assignments
        WHERE customer_id = c.customer_id AND status = 'ACTIVE'
        ORDER BY assigned_at DESC LIMIT 1
    ) a ON TRUE
    LEFT JOIN customer_opportunities o ON o.customer_id = c.customer_id AND o.status <> 'REPLACED'
    ORDER BY o.heat_score DESC NULLS LAST, o.last_seen_at DESC NULLS LAST
    """
)
_FACTS = text(
    """
    SELECT kind, ref_id, opportunity_id, session_id, code, value, value_code, evidence_quote, turn_index,
           status, source, is_current, at
    FROM customer_360_facts WHERE customer_id = :customer_id ORDER BY at
    """
)
_SESSIONS = text(
    """
    SELECT s.session_id, s.started_at, s.last_activity_at, s.status, s.ownership,
           so.kind, so.opportunity_id, COALESCE(so.needs_review, FALSE) AS needs_review, so.decided_by,
           cs.turn_count, cs.ask_counts, LEFT(sm.content, 280) AS summary, sm.content AS summary_full,
           s.last_quote_sent_at, cs.chosen_vehicle_id, rec.recommendations AS latest_recommendations,
           rec_first.first_at AS first_recommendation_at, fm.mentions AS feature_mentions
    FROM conversation_sessions s
    LEFT JOIN session_opportunity so ON so.session_id = s.session_id
    LEFT JOIN conversation_core_state cs ON cs.session_id = s.session_id
    LEFT JOIN conversation_summaries sm ON sm.session_id = s.session_id
    LEFT JOIN LATERAL (
        SELECT t.recommendations FROM conversation_turn_outcomes t
        WHERE t.session_id = s.session_id AND jsonb_array_length(t.recommendations) > 0
        ORDER BY t.created_at DESC LIMIT 1
    ) rec ON TRUE
    LEFT JOIN LATERAL (
        SELECT MIN(t.created_at) AS first_at FROM conversation_turn_outcomes t
        WHERE t.session_id = s.session_id AND jsonb_array_length(t.recommendations) > 0
    ) rec_first ON TRUE
    LEFT JOIN LATERAL (
        SELECT array_agg(m.raw_mention ORDER BY m.created_at) AS mentions FROM pending_feature_mentions m
        WHERE m.session_id = s.session_id
    ) fm ON TRUE
    WHERE s.customer_id = :customer_id
    ORDER BY s.last_activity_at DESC
    LIMIT 50
    """
)
_OPPORTUNITY_LIST = text(
    """
    SELECT o.opportunity_id, o.customer_id, cp.display_name, a.advisor_id, o.vehicle_type, o.buyer_for, o.status,
           o.stage, o.heat_score, o.heat_band, o.slots_snapshot, o.last_seen_at,
           COALESCE((
               SELECT array_agg(DISTINCT b.label ORDER BY b.label)
               FROM session_opportunity so
               JOIN conversation_turn_bottlenecks b ON b.session_id = so.session_id AND b.status <> 'INCORRECT'
               WHERE so.opportunity_id = o.opportunity_id
           ), ARRAY[]::varchar[]) AS barriers,
           EXISTS (
               SELECT 1 FROM session_opportunity so WHERE so.opportunity_id = o.opportunity_id AND so.needs_review
           ) AS needs_review,
           (SELECT COUNT(*) FROM conversation_sessions cs WHERE cs.customer_id = o.customer_id) AS sessions_count,
           (cp.phone IS NOT NULL AND cp.phone <> '') AS has_phone,
           EXISTS (
               SELECT 1 FROM conversation_sessions cs
               WHERE cs.customer_id = o.customer_id AND cs.status = 'ACTIVE' AND cs.ownership = 'PENDING_HANDOFF'
           ) AS waiting,
           EXISTS (
               SELECT 1 FROM test_drive_bookings tb
               WHERE tb.customer_id = o.customer_id AND tb.status <> 'CANCELLED' AND tb.scheduled_at >= :now
           ) AS has_test_drive,
           EXISTS (
               SELECT 1 FROM test_drive_bookings tb WHERE tb.customer_id = o.customer_id AND tb.status = 'REQUESTED'
           ) AS booking_requested,
           (
               SELECT t.recommendations -> 0 ->> 'display_name'
               FROM conversation_turn_outcomes t
               JOIN session_opportunity so ON so.session_id = t.session_id
               WHERE so.opportunity_id = o.opportunity_id AND jsonb_array_length(t.recommendations) > 0
               ORDER BY t.created_at DESC LIMIT 1
           ) AS top_vehicle_name
    FROM customer_opportunities o
    LEFT JOIN customer_profiles cp ON cp.customer_id = o.customer_id
    LEFT JOIN LATERAL (
        SELECT advisor_id FROM customer_advisor_assignments
        WHERE customer_id = o.customer_id AND status = 'ACTIVE'
        ORDER BY assigned_at DESC LIMIT 1
    ) a ON TRUE
    WHERE o.status IN ('OPEN', 'DORMANT')
      AND (:all_scope OR a.advisor_id IN :advisor_ids)
      AND (CAST(:band AS varchar) IS NULL OR o.heat_band = :band)
      AND (NOT :only_waiting OR EXISTS (
          SELECT 1 FROM conversation_sessions cs
          WHERE cs.customer_id = o.customer_id AND cs.status = 'ACTIVE' AND cs.ownership = 'PENDING_HANDOFF'
      ))
      AND (NOT :only_test_drive OR EXISTS (
          SELECT 1 FROM test_drive_bookings tb
          WHERE tb.customer_id = o.customer_id AND tb.status <> 'CANCELLED' AND tb.scheduled_at >= :now
      ))
    ORDER BY o.heat_score DESC, o.last_seen_at DESC
    LIMIT :limit
    """
).bindparams(bindparam("advisor_ids", expanding=True))
#: Tab "Đã nhận" (plan §20): MỖI khách tư vấn viên đang phụ trách — xuất phát từ PHÂN CÔNG, không
#: từ cơ hội, nên khách vừa nhận mà chưa chat lượt nào vẫn có mặt. Cơ hội nóng nhất (nếu có) ghép
#: vào để có độ nóng/giai đoạn/rào cản. MỘT câu SQL, không N+1.
_MY_CUSTOMERS = text(
    """
    SELECT a.customer_id, cp.display_name, cp.email, a.advisor_id, a.assigned_at,
           o.opportunity_id, o.vehicle_type, o.buyer_for, o.status, o.stage, o.heat_score, o.heat_band,
           o.slots_snapshot,
           COALESCE(st.last_seen_at, o.last_seen_at, a.assigned_at) AS last_seen_at,
           COALESCE((
               SELECT array_agg(DISTINCT b.label ORDER BY b.label)
               FROM session_opportunity so
               JOIN conversation_turn_bottlenecks b ON b.session_id = so.session_id AND b.status <> 'INCORRECT'
               WHERE so.opportunity_id = o.opportunity_id
           ), ARRAY[]::varchar[]) AS barriers,
           EXISTS (
               SELECT 1 FROM session_opportunity so WHERE so.opportunity_id = o.opportunity_id AND so.needs_review
           ) AS needs_review,
           COALESCE(st.sessions_count, 0) AS sessions_count,
           (cp.phone IS NOT NULL AND cp.phone <> '') AS has_phone,
           COALESCE(st.waiting, FALSE) AS waiting,
           EXISTS (
               SELECT 1 FROM test_drive_bookings tb
               WHERE tb.customer_id = a.customer_id AND tb.status <> 'CANCELLED' AND tb.scheduled_at >= :now
           ) AS has_test_drive,
           EXISTS (
               SELECT 1 FROM test_drive_bookings tb WHERE tb.customer_id = a.customer_id AND tb.status = 'REQUESTED'
           ) AS booking_requested,
           (
               SELECT t.recommendations -> 0 ->> 'display_name'
               FROM conversation_turn_outcomes t
               JOIN session_opportunity so ON so.session_id = t.session_id
               WHERE so.opportunity_id = o.opportunity_id AND jsonb_array_length(t.recommendations) > 0
               ORDER BY t.created_at DESC LIMIT 1
           ) AS top_vehicle_name
    FROM customer_advisor_assignments a
    LEFT JOIN customer_profiles cp ON cp.customer_id = a.customer_id
    LEFT JOIN LATERAL (
        SELECT * FROM customer_opportunities
        WHERE customer_id = a.customer_id AND status IN ('OPEN', 'DORMANT')
        ORDER BY heat_score DESC, last_seen_at DESC LIMIT 1
    ) o ON TRUE
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS sessions_count, MAX(s.last_activity_at) AS last_seen_at,
               BOOL_OR(s.status = 'ACTIVE' AND s.ownership = 'PENDING_HANDOFF') AS waiting
        FROM conversation_sessions s WHERE s.customer_id = a.customer_id
    ) st ON TRUE
    WHERE a.status = 'ACTIVE'
      AND (:all_scope OR a.advisor_id IN :advisor_ids)
      AND (CAST(:band AS varchar) IS NULL OR o.heat_band = :band)
      AND (NOT :only_waiting OR COALESCE(st.waiting, FALSE))
      AND (NOT :only_test_drive OR EXISTS (
          SELECT 1 FROM test_drive_bookings tb
          WHERE tb.customer_id = a.customer_id AND tb.status <> 'CANCELLED' AND tb.scheduled_at >= :now
      ))
    ORDER BY COALESCE(st.waiting, FALSE) DESC, o.heat_score DESC NULLS LAST,
             COALESCE(st.last_seen_at, o.last_seen_at, a.assigned_at) DESC
    LIMIT :limit
    """
).bindparams(bindparam("advisor_ids", expanding=True))
#: Bốn thẻ số đầu màn "Khách cần xử lý" — MỘT câu, cùng phạm vi TVV với `_OPPORTUNITY_LIST`
#: (khách có phân công ACTIVE cho TVV; Admin xem tất cả).
_OPPORTUNITY_SUMMARY = text(
    """
    WITH scope AS (
        SELECT DISTINCT c.customer_id FROM (
            SELECT o.customer_id FROM customer_opportunities o WHERE o.status IN ('OPEN', 'DORMANT')
            UNION SELECT a.customer_id FROM customer_advisor_assignments a WHERE a.status = 'ACTIVE'
        ) c
        LEFT JOIN LATERAL (
            SELECT advisor_id FROM customer_advisor_assignments
            WHERE customer_id = c.customer_id AND status = 'ACTIVE'
            ORDER BY assigned_at DESC LIMIT 1
        ) a ON TRUE
        WHERE :all_scope OR a.advisor_id IN :advisor_ids
    )
    SELECT
        (SELECT COUNT(DISTINCT o.customer_id) FROM customer_opportunities o JOIN scope USING (customer_id)
          WHERE o.status = 'OPEN' AND o.heat_band = 'HOT') AS hot,
        (SELECT COUNT(DISTINCT s.customer_id) FROM conversation_sessions s JOIN scope USING (customer_id)
          WHERE s.status = 'ACTIVE' AND s.ownership = 'PENDING_HANDOFF') AS waiting,
        (SELECT COUNT(*) FROM test_drive_bookings tb JOIN scope USING (customer_id)
          WHERE tb.status <> 'CANCELLED' AND tb.scheduled_at >= :now AND tb.scheduled_at < :soon) AS test_drives_48h,
        (SELECT COUNT(*) FROM out_of_scope_log l
          JOIN conversation_sessions s ON s.session_id = l.session_id
          JOIN scope ON scope.customer_id = s.customer_id
          WHERE l.classification IN ('MISSING_DATA', 'OUT_OF_SCOPE') AND l.created_at >= :since) AS unanswered
    """
).bindparams(bindparam("advisor_ids", expanding=True))
_PICKER = text(
    """
    SELECT s.customer_id, cp.display_name, cp.phone, a.advisor_id, MAX(s.last_activity_at) AS last_seen_at,
           COUNT(*) AS sessions_count,
           (SELECT o.heat_band FROM customer_opportunities o
             WHERE o.customer_id = s.customer_id AND o.status = 'OPEN'
             ORDER BY o.heat_score DESC LIMIT 1) AS heat_band,
           (SELECT MAX(o.heat_score) FROM customer_opportunities o
             WHERE o.customer_id = s.customer_id AND o.status = 'OPEN') AS heat_score
    FROM conversation_sessions s
    LEFT JOIN customer_profiles cp ON cp.customer_id = s.customer_id
    LEFT JOIN LATERAL (
        SELECT advisor_id FROM customer_advisor_assignments
        WHERE customer_id = s.customer_id AND status = 'ACTIVE'
        ORDER BY assigned_at DESC LIMIT 1
    ) a ON TRUE
    WHERE s.customer_id NOT LIKE 'anon-%'
      AND (CAST(:query AS varchar) IS NULL
           OR s.customer_id ILIKE :pattern OR cp.display_name ILIKE :pattern)
    GROUP BY s.customer_id, cp.display_name, cp.phone, a.advisor_id
    ORDER BY heat_score DESC NULLS LAST, last_seen_at DESC
    LIMIT :limit
    """
)
_OWNER = {
    "session": text(
        """
        SELECT s.customer_id, a.advisor_id FROM conversation_sessions s
        LEFT JOIN customer_advisor_assignments a ON a.customer_id = s.customer_id AND a.status = 'ACTIVE'
        WHERE s.session_id = CAST(:ref AS uuid)
        """
    ),
    "insight": text(
        """
        SELECT i.customer_id, a.advisor_id FROM customer_insights i
        LEFT JOIN customer_advisor_assignments a ON a.customer_id = i.customer_id AND a.status = 'ACTIVE'
        WHERE i.insight_id = CAST(:ref AS uuid)
        """
    ),
    "offer": text(
        """
        SELECT f.customer_id, a.advisor_id FROM opportunity_offers f
        LEFT JOIN customer_advisor_assignments a ON a.customer_id = f.customer_id AND a.status = 'ACTIVE'
        WHERE f.offer_id = CAST(:ref AS uuid)
        """
    ),
    "opportunity": text(
        """
        SELECT o.customer_id, a.advisor_id FROM customer_opportunities o
        LEFT JOIN customer_advisor_assignments a ON a.customer_id = o.customer_id AND a.status = 'ACTIVE'
        WHERE o.opportunity_id = CAST(:ref AS uuid)
        """
    ),
}
_QUALITY_INSIGHTS = text(
    """
    SELECT i.field,
           COUNT(DISTINCT i.insight_id) AS total,
           COUNT(DISTINCT f.insight_id) FILTER (WHERE f.kind = 'INSIGHT_WRONG') AS wrong
    FROM customer_insights i
    LEFT JOIN customer360_feedback f ON f.insight_id = i.insight_id
    WHERE i.source = 'LLM' AND i.extracted_at >= :since
    GROUP BY i.field ORDER BY i.field
    """
)
_QUALITY_ATTACH = text(
    """
    SELECT so.decided_by, COUNT(*) AS total FROM session_opportunity so
    WHERE so.decided_at >= :since GROUP BY so.decided_by
    """
)
_QUALITY_CORRECTIONS = text(
    """
    SELECT COALESCE(previous_decided_by, 'NONE') AS decided_by, COUNT(*) AS corrected FROM customer360_feedback
    WHERE kind IN ('SESSION_MOVED', 'SESSION_SPLIT') AND created_at >= :since
    GROUP BY COALESCE(previous_decided_by, 'NONE')
    """
)
_QUALITY_SAMPLES = text(
    """
    SELECT i.insight_id::text AS insight_id, i.field, i.value, i.evidence_quote, f.note, f.created_at
    FROM customer360_feedback f JOIN customer_insights i ON i.insight_id = f.insight_id
    WHERE f.kind = 'INSIGHT_WRONG' AND f.created_at >= :since
    ORDER BY f.created_at DESC LIMIT 20
    """
)
_METRICS_STAGE = text(
    "SELECT stage, COUNT(*) FROM customer_opportunities WHERE status IN ('OPEN','DORMANT','WON') GROUP BY stage"
)
_METRICS_HEAT = text("SELECT heat_band, COUNT(*) FROM customer_opportunities WHERE status = 'OPEN' GROUP BY heat_band")
_METRICS_BARRIERS = text(
    """
    SELECT label, COUNT(*) FROM conversation_turn_bottlenecks
    WHERE status <> 'INCORRECT' AND created_at >= :since GROUP BY label ORDER BY COUNT(*) DESC
    """
)
_METRICS_WORKLOAD = text(
    """
    SELECT a.advisor_id,
           COUNT(DISTINCT a.customer_id) AS customers,
           COUNT(DISTINCT o.customer_id) FILTER (WHERE o.heat_band = 'HOT' AND o.status = 'OPEN') AS hot_customers,
           COUNT(DISTINCT s.session_id) FILTER (WHERE s.ownership = 'PENDING_HANDOFF' AND s.status = 'ACTIVE') AS waiting
    FROM customer_advisor_assignments a
    LEFT JOIN customer_opportunities o ON o.customer_id = a.customer_id
    LEFT JOIN conversation_sessions s ON s.customer_id = a.customer_id
    WHERE a.status = 'ACTIVE'
    GROUP BY a.advisor_id
    ORDER BY hot_customers DESC, customers DESC
    """
)
_METRICS_TOTALS = text(
    """
    SELECT (SELECT COUNT(*) FROM conversation_sessions) AS conversations,
           (SELECT COUNT(DISTINCT customer_id) FROM conversation_sessions) AS customers,
           (SELECT COUNT(*) FROM customer_opportunities WHERE status = 'OPEN') AS open_opportunities,
           (SELECT COUNT(*) FROM test_drive_bookings WHERE status <> 'CANCELLED') AS test_drives,
           (SELECT COUNT(*) FROM session_opportunity WHERE needs_review) AS needs_review
    """
)


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


class CustomerProfileBundle:
    """Kết quả 3 câu đọc hồ sơ — đầu vào của `domain.customer_overview.build_overview`."""

    def __init__(
        self,
        header: HeaderRow,
        opportunities: list[OpportunityRow],
        facts: list[FactRow],
        sessions: list[SessionRowIn],
    ) -> None:
        self.header = header
        self.opportunities = opportunities
        self.facts = facts
        self.sessions = sessions


class SqlAlchemyCustomer360Query:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_profile(self, customer_id: str) -> CustomerProfileBundle:
        async with self._session_factory() as session:
            head_rows = (
                (await session.execute(_HEADER_AND_OPPORTUNITIES, {"customer_id": customer_id})).mappings().all()
            )
            fact_rows = (await session.execute(_FACTS, {"customer_id": customer_id})).mappings().all()
            session_rows = (await session.execute(_SESSIONS, {"customer_id": customer_id})).mappings().all()
        first = head_rows[0]
        header = HeaderRow(
            customer_id=customer_id,
            display_name=first["display_name"],
            phone=first["phone"],
            assigned_advisor_id=first["advisor_id"],
            address=first["address"],
        )
        opportunities = [
            OpportunityRow(
                opportunity_id=str(row["opportunity_id"]),
                vehicle_type=row["vehicle_type"],
                buyer_for=row["buyer_for"],
                status=row["status"],
                stage=row["stage"],
                heat_score=int(row["heat_score"]),
                heat_band=row["heat_band"],
                heat_breakdown=row["heat_breakdown"] or [],
                slots=row["slots_snapshot"] or {},
                slot_history=row["slot_history"] or [],
                last_seen_at=row["last_seen_at"],
            )
            for row in head_rows
            if row["opportunity_id"] is not None
        ]
        facts = [
            FactRow(
                kind=row["kind"],
                ref_id=row["ref_id"],
                opportunity_id=row["opportunity_id"],
                session_id=row["session_id"],
                code=row["code"],
                value=row["value"],
                value_code=row["value_code"],
                evidence_quote=row["evidence_quote"],
                turn_index=int(row["turn_index"]) if row["turn_index"] is not None else None,
                status=row["status"],
                source=row["source"],
                is_current=bool(row["is_current"]),
                at=row["at"],
            )
            for row in fact_rows
        ]
        sessions = [
            SessionRowIn(
                session_id=str(row["session_id"]),
                started_at=row["started_at"],
                last_activity_at=row["last_activity_at"],
                status=row["status"],
                ownership=row["ownership"],
                kind=row["kind"],
                opportunity_id=_str(row["opportunity_id"]),
                needs_review=bool(row["needs_review"]),
                decided_by=row["decided_by"],
                turn_count=int(row["turn_count"]) if row["turn_count"] is not None else None,
                ask_counts=row["ask_counts"] or {},
                summary=row["summary"],
                summary_full=row["summary_full"],
                last_quote_sent_at=row["last_quote_sent_at"],
                chosen_vehicle_id=_str(row["chosen_vehicle_id"]),
                latest_recommendations=list(row["latest_recommendations"] or []),
                first_recommendation_at=row["first_recommendation_at"],
                feature_mentions=list(row["feature_mentions"] or []),
            )
            for row in session_rows
        ]
        return CustomerProfileBundle(header, opportunities, facts, sessions)

    async def owner(self, kind: str, ref: str) -> tuple[str, set[str]] | None:
        """Khách sở hữu một phiên/insight/cơ hội và các TVV đang được giao khách đó."""

        async with self._session_factory() as session:
            rows = (await session.execute(_OWNER[kind], {"ref": ref})).all()
        if not rows:
            return None
        return rows[0][0], {row[1] for row in rows if row[1]}

    async def list_opportunities(
        self,
        *,
        advisor_ids: Sequence[str] | None,
        band: str | None,
        limit: int,
        now: datetime,
        only_waiting: bool = False,
        only_test_drive: bool = False,
    ) -> list[dict[str, Any]]:
        params = {
            "all_scope": advisor_ids is None,
            "advisor_ids": list(advisor_ids or ["__none__"]),
            "band": band,
            "limit": limit,
            "now": now,
            "only_waiting": only_waiting,
            "only_test_drive": only_test_drive,
        }
        async with self._session_factory() as session:
            rows = (await session.execute(_OPPORTUNITY_LIST, params)).mappings().all()
        return [
            {
                "opportunity_id": str(row["opportunity_id"]),
                "customer_id": row["customer_id"],
                "display_name": row["display_name"],
                "assigned_advisor_id": row["advisor_id"],
                "vehicle_type": row["vehicle_type"],
                "buyer_for": row["buyer_for"],
                "status": row["status"],
                "stage": row["stage"],
                "heat_score": int(row["heat_score"]),
                "heat_band": row["heat_band"],
                "slots": {
                    key: value for key, value in (row["slots_snapshot"] or {}).items() if key != "purpose_bucket"
                },
                "barriers": list(row["barriers"] or []),
                "needs_review": bool(row["needs_review"]),
                "last_seen_at": row["last_seen_at"],
                "sessions_count": int(row["sessions_count"]),
                "has_phone": bool(row["has_phone"]),
                "waiting": bool(row["waiting"]),
                "has_test_drive": bool(row["has_test_drive"]),
                "booking_requested": bool(row["booking_requested"]),
                "top_vehicle_name": row["top_vehicle_name"],
            }
            for row in rows
        ]

    async def list_my_customers(
        self,
        *,
        advisor_ids: Sequence[str] | None,
        band: str | None,
        limit: int,
        now: datetime,
        only_waiting: bool = False,
        only_test_drive: bool = False,
    ) -> list[dict[str, Any]]:
        params = {
            "all_scope": advisor_ids is None,
            "advisor_ids": list(advisor_ids or ["__none__"]),
            "band": band,
            "limit": limit,
            "now": now,
            "only_waiting": only_waiting,
            "only_test_drive": only_test_drive,
        }
        async with self._session_factory() as session:
            rows = (await session.execute(_MY_CUSTOMERS, params)).mappings().all()
        return [
            {
                "customer_id": row["customer_id"],
                "display_name": row["display_name"],
                "email": row["email"],
                "assigned_advisor_id": row["advisor_id"],
                "assigned_at": row["assigned_at"],
                "opportunity_id": _str(row["opportunity_id"]),
                "vehicle_type": row["vehicle_type"],
                "buyer_for": row["buyer_for"],
                "status": row["status"],
                "stage": row["stage"],
                "heat_score": int(row["heat_score"]) if row["heat_score"] is not None else None,
                "heat_band": row["heat_band"],
                "slots": {
                    key: value for key, value in (row["slots_snapshot"] or {}).items() if key != "purpose_bucket"
                },
                "barriers": list(row["barriers"] or []),
                "needs_review": bool(row["needs_review"]),
                "last_seen_at": row["last_seen_at"],
                "sessions_count": int(row["sessions_count"]),
                "has_phone": bool(row["has_phone"]),
                "waiting": bool(row["waiting"]),
                "has_test_drive": bool(row["has_test_drive"]),
                "booking_requested": bool(row["booking_requested"]),
                "top_vehicle_name": row["top_vehicle_name"],
            }
            for row in rows
        ]

    async def opportunity_summary(self, *, advisor_ids: Sequence[str] | None, now: datetime) -> dict[str, int]:
        params = {
            "all_scope": advisor_ids is None,
            "advisor_ids": list(advisor_ids or ["__none__"]),
            "now": now,
            "soon": now + timedelta(hours=48),
            "since": now - timedelta(days=7),
        }
        async with self._session_factory() as session:
            row = (await session.execute(_OPPORTUNITY_SUMMARY, params)).mappings().one()
        return {key: int(value or 0) for key, value in row.items()}

    async def picker(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        cleaned = (query or "").strip() or None
        params = {"query": cleaned, "pattern": f"%{cleaned}%" if cleaned else "%", "limit": limit}
        async with self._session_factory() as session:
            rows = (await session.execute(_PICKER, params)).mappings().all()
        return [dict(row) for row in rows]

    async def extraction_quality(self, since: datetime) -> dict[str, Any]:
        """Tab "Chất lượng trích xuất" (Phase 6): insight bị TVV báo sai, gắn phiên bị TVV sửa."""

        async with self._session_factory() as session:
            insights = (await session.execute(_QUALITY_INSIGHTS, {"since": since})).mappings().all()
            attach = dict((await session.execute(_QUALITY_ATTACH, {"since": since})).all())
            corrections = dict((await session.execute(_QUALITY_CORRECTIONS, {"since": since})).all())
            samples = (await session.execute(_QUALITY_SAMPLES, {"since": since})).mappings().all()
        return {
            "insights_total": sum(int(row["total"]) for row in insights),
            "insights_reported_wrong": sum(int(row["wrong"]) for row in insights),
            "by_field": [
                {"field": row["field"], "total": int(row["total"]), "wrong": int(row["wrong"])} for row in insights
            ],
            "attach_total": sum(int(value) for value in attach.values()),
            "attach_by_decider": {str(key): int(value) for key, value in attach.items()},
            "corrected_by_decider": {str(key): int(value) for key, value in corrections.items()},
            "samples": [dict(row) for row in samples],
        }

    async def metrics(self, now: datetime, window_days: int) -> dict[str, Any]:
        async with self._session_factory() as session:
            stages = dict((await session.execute(_METRICS_STAGE)).all())
            heat = dict((await session.execute(_METRICS_HEAT)).all())
            barriers = (await session.execute(_METRICS_BARRIERS, {"since": now - timedelta(days=window_days)})).all()
            workload = (await session.execute(_METRICS_WORKLOAD)).mappings().all()
            totals = (await session.execute(_METRICS_TOTALS)).mappings().one()
        return {
            "stages": {str(key): int(value) for key, value in stages.items()},
            "heat": {str(key): int(value) for key, value in heat.items()},
            "barriers": [{"code": str(label), "count": int(count)} for label, count in barriers],
            "workload": [
                {
                    "advisor_id": row["advisor_id"],
                    "customers": int(row["customers"]),
                    "hot_customers": int(row["hot_customers"]),
                    "waiting_sessions": int(row["waiting"]),
                }
                for row in workload
            ],
            "totals": {key: int(value) for key, value in totals.items()},
        }


__all__ = ["CustomerProfileBundle", "SqlAlchemyCustomer360Query"]
