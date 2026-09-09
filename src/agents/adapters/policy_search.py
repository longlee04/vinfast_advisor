"""Scoped PostgreSQL hybrid search over reviewed Document policy evidence."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.ports import EmbeddingPort
from src.agents.tools.policy_search import reciprocal_rank_fusion
from src.document.infrastructure.models import DocumentRow, PolicyScopeRow, VehicleDocumentRow

_DATE_PATTERN = re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4})\b")


class SqlAlchemyPolicySearchAdapter:
    """Filter applicability first, then rank only ACTIVE literal evidence chunks."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding: EmbeddingPort,
    ) -> None:
        self._session_factory = session_factory
        self._embedding = embedding

    async def search(
        self,
        *,
        query: str,
        top_k: int = 5,
        category_filter: str | None = None,
        effective_after: str | None = None,
        vehicle_id: str | None = None,
    ) -> list[dict]:
        """Return cited chunks; unavailable vectors degrade to grounded BM25 only."""
        del effective_after
        if top_k < 1 or not query.strip() or not vehicle_id:
            return []
        today = datetime.now(UTC).date()
        eligibility_date = _eligibility_date(query)
        filters = [
            VehicleDocumentRow.status == "ACTIVE",
            VehicleDocumentRow.policy_scope_id.is_not(None),
            VehicleDocumentRow.source_url.is_not(None),
            PolicyScopeRow.status == "ACTIVE",
            DocumentRow.archived_at.is_(None),
            DocumentRow.source_authority.in_(("OFFICIAL", "INTERNAL_APPROVED")),
            or_(PolicyScopeRow.policy_active_from.is_(None), PolicyScopeRow.policy_active_from <= today),
            or_(PolicyScopeRow.policy_active_to.is_(None), PolicyScopeRow.policy_active_to >= today),
            _cohort_filter(eligibility_date),
        ]
        topics = _topics_for_query(query)
        if topics:
            filters.append(PolicyScopeRow.topic.in_(topics))
        if category_filter:
            filters.append(PolicyScopeRow.policy_type == category_filter.casefold())
        filters.append(VehicleDocumentRow.vehicle_id == vehicle_id)
        usage_type = _usage_for_query(query)
        filters.append(
            PolicyScopeRow.usage_type.in_((usage_type, "ANY"))
            if usage_type
            else PolicyScopeRow.usage_type == "ANY"
        )
        ownership_model = _ownership_for_query(query)
        filters.append(
            PolicyScopeRow.ownership_model == ownership_model
            if ownership_model
            else or_(
                PolicyScopeRow.ownership_model.is_(None),
                PolicyScopeRow.ownership_model == "NOT_APPLICABLE",
            )
        )

        base = (
            select(VehicleDocumentRow)
            .join(PolicyScopeRow, PolicyScopeRow.scope_id == VehicleDocumentRow.policy_scope_id)
            .join(DocumentRow, DocumentRow.id == VehicleDocumentRow.source_document_id)
            .where(*filters)
        )
        pool_size = max(top_k * 4, 20)
        async with self._session_factory() as session:
            bm25_rows = (
                await session.execute(
                    base.order_by(
                        func.ts_rank(
                            VehicleDocumentRow.content_tsv,
                            func.plainto_tsquery("simple", query),
                        ).desc(),
                        VehicleDocumentRow.document_id,
                    ).limit(pool_size)
                )
            ).scalars().all()
            vector_rows: list[VehicleDocumentRow] = []
            try:
                vectors = await self._embedding.embed([query])
                if vectors and len(vectors[0]) == 1024:
                    vector_rows = (
                        await session.execute(
                            base.where(VehicleDocumentRow.embedding.is_not(None))
                            .order_by(VehicleDocumentRow.embedding.cosine_distance(vectors[0]))
                            .limit(pool_size)
                        )
                    ).scalars().all()
            except RuntimeError:
                vector_rows = []

            bm25_ids = [str(row.document_id) for row in bm25_rows]
            vector_ids = [str(row.document_id) for row in vector_rows]
            ordered_ids = reciprocal_rank_fusion(bm25_ids, vector_ids)[:top_k]
            if not ordered_ids:
                return []
            details = (
                await session.execute(
                    select(VehicleDocumentRow, PolicyScopeRow)
                    .join(PolicyScopeRow, PolicyScopeRow.scope_id == VehicleDocumentRow.policy_scope_id)
                    .where(VehicleDocumentRow.document_id.in_(ordered_ids))
                )
            ).all()
        by_id = {str(chunk.document_id): (chunk, scope) for chunk, scope in details}
        return [
            {
                "chunk_id": chunk_id,
                "source_file": by_id[chunk_id][0].title,
                "source_url": by_id[chunk_id][0].source_url,
                "source_revision": by_id[chunk_id][0].source_revision,
                "policy_category": by_id[chunk_id][1].policy_type,
                "topic": by_id[chunk_id][1].topic,
                "scope_id": str(by_id[chunk_id][1].scope_id),
                "eligibility_basis": by_id[chunk_id][1].eligibility_basis,
                "chunk_text": by_id[chunk_id][0].content,
            }
            for chunk_id in ordered_ids
            if chunk_id in by_id
        ]


def _eligibility_date(query: str) -> date | None:
    match = _DATE_PATTERN.search(query)
    if match is None:
        return None
    try:
        return date(int(match["year"]), int(match["month"]), int(match["day"]))
    except ValueError:
        return None


def _cohort_filter(eligibility_date: date | None):  # noqa: ANN202
    if eligibility_date is None:
        return PolicyScopeRow.is_current_default.is_(True)
    return and_(
        PolicyScopeRow.eligibility_basis != "NONE",
        or_(PolicyScopeRow.eligibility_from.is_(None), PolicyScopeRow.eligibility_from <= eligibility_date),
        or_(PolicyScopeRow.eligibility_to.is_(None), PolicyScopeRow.eligibility_to >= eligibility_date),
    )


def _topics_for_query(query: str) -> tuple[str, ...]:
    normalized = query.casefold()
    if "bảo hành" in normalized or "bao hanh" in normalized:
        if "pin" in normalized:
            return ("battery_warranty",)
        if "phụ tùng" in normalized or "phu tung" in normalized:
            return ("spare_part_warranty",)
        return ("vehicle_warranty",)
    if "đổi pin" in normalized or "doi pin" in normalized or "swap" in normalized:
        return ("battery_swap", "battery_replacement")
    if "thuê pin" in normalized or "thue pin" in normalized:
        return ("battery_rental", "battery_contract")
    if "mua pin" in normalized:
        return ("battery_purchase",)
    if "sạc" in normalized or "sac" in normalized:
        return ("battery_charging",)
    return ()


def _usage_for_query(query: str) -> str | None:
    normalized = query.casefold()
    if any(marker in normalized for marker in ("grab", "dịch vụ", "dich vu", "kinh doanh")):
        return "COMMERCIAL"
    if any(marker in normalized for marker in ("cá nhân", "ca nhan", "gia đình", "gia dinh")):
        return "STANDARD"
    return None


def _ownership_for_query(query: str) -> str | None:
    normalized = query.casefold()
    if "đổi pin" in normalized or "doi pin" in normalized or "swap" in normalized:
        return "SWAP"
    if "thuê pin" in normalized or "thue pin" in normalized:
        return "SUBSCRIPTION"
    if "mua pin" in normalized:
        return "PURCHASE"
    if "kèm pin" in normalized or "kem pin" in normalized or "pin kèm xe" in normalized:
        return "INCLUDED"
    return None


__all__ = ["SqlAlchemyPolicySearchAdapter"]
