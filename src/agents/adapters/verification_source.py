"""[A6-1] Run-scoped evidence source for post-synthesis verification."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.models import RunEvidenceRow, RunSnapshotRow
from src.agents.services.verification import VerificationEvidence


class SqlAlchemyVerificationDataSource:
    """Load immutable evidence rows belonging to one agent run."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        # Mở session mới mỗi lần đọc để lấy evidence mới nhất, không giữ
        # transaction sống suốt vòng đời adapter.
        self._session_factory = session_factory

    async def load_evidence(self, run_id: UUID) -> Sequence[VerificationEvidence]:
        """Return only evidence persisted for requested run."""

        async with self._session_factory() as session:
            rows = (await session.execute(select(RunEvidenceRow).where(RunEvidenceRow.run_id == run_id))).scalars()
            return [
                VerificationEvidence(
                    evidence_id=row.evidence_id,
                    fact_code=row.fact_code,
                    value_text=row.value_text,
                )
                for row in rows
            ]

    async def load_vehicle_names(self, run_id: UUID) -> Sequence[str]:
        """Read model names from immutable snapshots belonging to this run."""

        async with self._session_factory() as session:
            payloads = (
                await session.execute(select(RunSnapshotRow.payload).where(RunSnapshotRow.run_id == run_id))
            ).scalars()
            names: list[str] = []
            for payload in payloads:
                for candidate in (payload or {}).get("candidates", []):
                    model_name = candidate.get("model_name")
                    if isinstance(model_name, str) and model_name.strip():
                        names.append(model_name)
            return names
