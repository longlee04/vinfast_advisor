"""Read immutable synthesis facts and brochure excerpts from run evidence."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.models import RunEvidenceRow, RunSnapshotRow
from src.agents.services.snapshotting import QUOTE_FACT_CODE, parse_snapshot
from src.agents.services.synthesis import (
    PLACEHOLDER_UNITS,
    SynthesisFact,
    SynthesisQuote,
)
from src.document.infrastructure.models import VehicleDocumentRow
from src.products.infrastructure.models import VehiclePriceRow

PRICE_SOURCE_TABLE = "vehicle_prices"
DOCUMENT_SOURCE_TABLE = "vehicle_documents"


def _owner_vehicle(
    row: RunEvidenceRow,
    vehicle_ids: tuple[UUID, ...],
    price_owners: dict[UUID, UUID],
    document_owners: dict[UUID, UUID],
) -> UUID | None:
    """Evidence của một run trải phẳng mọi candidate, nên phải quy về từng xe.

    Không có `source_id` thì không chứng minh được thuộc xe nào: loại, vì để lọt
    sẽ làm hai xe cùng đóng góp một `fact_code` và tầng tổng hợp vỡ.
    """

    if row.source_id is None:
        return None
    source_id = UUID(str(row.source_id))
    if row.source_table == PRICE_SOURCE_TABLE:
        return price_owners.get(source_id)
    if row.source_table == DOCUMENT_SOURCE_TABLE:
        return document_owners.get(source_id)
    return source_id if source_id in vehicle_ids else None


class SqlAlchemySynthesisDataSource:
    """Load synthesis evidence belonging to one advisory run."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        # Mở session mới mỗi lần đọc để lấy evidence mới nhất, không giữ
        # transaction sống suốt vòng đời adapter.
        self._session_factory = session_factory

    async def load_vehicle_name(self, *, run_id: UUID, vehicle_id: UUID) -> str | None:
        """Read the selected model name from the latest immutable run snapshot."""

        async with self._session_factory() as session:
            snapshot_row = (
                await session.execute(
                    select(RunSnapshotRow)
                    .where(RunSnapshotRow.run_id == run_id)
                    .order_by(RunSnapshotRow.captured_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snapshot_row is None:
                return None
            snapshot = parse_snapshot(
                {
                    **snapshot_row.payload,
                    "captured_at": snapshot_row.captured_at,
                }
            )
            for candidate in snapshot.candidates:
                if candidate.vehicle_id == vehicle_id:
                    return candidate.model_name.strip() or None
            return None

    async def load_facts(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> Sequence[SynthesisFact]:
        """Map allowlisted numeric evidence into facts, mỗi fact mang đúng xe của nó."""

        if not vehicle_ids:
            return []
        async with self._session_factory() as session:
            rows = list(
                (await session.execute(select(RunEvidenceRow).where(RunEvidenceRow.run_id == run_id))).scalars()
            )
            price_owners = await self._price_owners(session, rows, vehicle_ids)
            document_owners = await self._document_owners(session, vehicle_ids)
            facts: list[SynthesisFact] = []
            for row in rows:
                unit = PLACEHOLDER_UNITS.get(row.fact_code)
                if unit is None:
                    continue
                owner = _owner_vehicle(row, vehicle_ids, price_owners, document_owners)
                if owner is None:
                    continue
                try:
                    Decimal(row.value_text)
                except InvalidOperation:
                    continue
                facts.append(
                    SynthesisFact(
                        vehicle_id=owner,
                        fact_code=row.fact_code,
                        value_text=row.value_text,
                        unit=unit,
                        evidence_id=row.evidence_id,
                        source_record=f"{row.source_table}:{row.source_id}",
                    )
                )
            return facts

    async def _price_owners(
        self,
        session: AsyncSession,
        rows: Sequence[RunEvidenceRow],
        vehicle_ids: tuple[UUID, ...],
    ) -> dict[UUID, UUID]:
        """Giá tham chiếu `price_id`, không phải `vehicle_id`, nên phải quy chiếu lại."""

        if not any(row.source_table == PRICE_SOURCE_TABLE for row in rows):
            return {}
        found = (
            await session.execute(
                select(VehiclePriceRow.price_id, VehiclePriceRow.vehicle_id).where(
                    VehiclePriceRow.vehicle_id.in_([str(value) for value in vehicle_ids])
                )
            )
        ).all()
        return {UUID(str(price_id)): UUID(str(owner)) for price_id, owner in found}

    async def _document_owners(self, session: AsyncSession, vehicle_ids: tuple[UUID, ...]) -> dict[UUID, UUID]:
        """Quote ghi `source_id = document_id`; `run_evidence` không có cột xe."""

        found = (
            await session.execute(
                select(VehicleDocumentRow.document_id, VehicleDocumentRow.vehicle_id).where(
                    VehicleDocumentRow.vehicle_id.in_([str(value) for value in vehicle_ids])
                )
            )
        ).all()
        return {UUID(str(document_id)): UUID(str(owner)) for document_id, owner in found}

    async def load_quotes(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> Sequence[SynthesisQuote]:
        """Return non-empty DOC_EXCERPT evidence CỦA ĐÚNG các xe được hỏi."""

        if not vehicle_ids:
            return []
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(RunEvidenceRow).where(
                            RunEvidenceRow.run_id == run_id,
                            RunEvidenceRow.fact_code == QUOTE_FACT_CODE,
                        )
                    )
                ).scalars()
            )
            document_owners = await self._document_owners(session, vehicle_ids)
            quotes: list[SynthesisQuote] = []
            for row in rows:
                if not row.value_text.strip():
                    continue
                owner = _owner_vehicle(row, vehicle_ids, {}, document_owners)
                if owner is None:
                    continue
                quotes.append(
                    SynthesisQuote(
                        text=row.value_text,
                        evidence_id=row.evidence_id,
                        vehicle_id=owner,
                        source_record=f"{row.source_table}:{row.source_id}",
                    )
                )
            return quotes
