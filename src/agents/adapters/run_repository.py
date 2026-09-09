"""[A5-1/A5-2] `RunRepository` thật — vòng đời `agent_runs` và `run_snapshots`.

Snapshot là bản sao bất biến của số liệu tại thời điểm truy vấn: `save_snapshot`
chỉ chèn, không cập nhật hàng cũ, để một run đã chốt không đổi số khi catalog đổi.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import CandidateInput, EvidenceInput, ScoreInput
from src.agents.models import (
    AgentRunRow,
    RunCandidateRow,
    RunEvidenceRow,
    RunSnapshotRow,
    ScoringResultRow,
    TcoEstimateRow,
)
from src.agents.ports import ClockPort
from src.agents.tools.tco import DetailedTcoResult


class SqlAlchemyRunRepository:
    """Implement `ports.RunRepository` trên một `AsyncSession` đã trong transaction."""

    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self.session = session
        self.clock = clock

    async def create_run(self, session_id: str) -> UUID:
        """Mở một run mới ở state đầu `CAPTURING` (mục 5, `agent_0003`)."""
        now = self.clock.now()
        run_id = uuid4()
        self.session.add(
            AgentRunRow(
                run_id=run_id,
                session_id=UUID(session_id),
                state="CAPTURING",
                created_at=now,
                updated_at=now,
            )
        )
        await self.session.flush()
        return run_id

    async def set_state(self, run_id: UUID, state: str) -> None:
        """Chuyển state của run; domain giữ luật chuyển trạng thái."""
        await self.session.execute(
            update(AgentRunRow).where(AgentRunRow.run_id == run_id).values(state=state, updated_at=self.clock.now())
        )

    async def save_snapshot(self, run_id: UUID, payload: dict) -> None:
        """Chèn snapshot mới; không ghi đè bản cũ vì snapshot phải bất biến."""
        now = self.clock.now()
        self.session.add(
            RunSnapshotRow(
                snapshot_id=uuid4(),
                run_id=run_id,
                captured_at=now,
                payload=payload,
                created_at=now,
            )
        )
        await self.session.flush()

    async def save_evidence(self, run_id: UUID, facts: Sequence[EvidenceInput]) -> None:
        """Chèn evidence phẳng cho một run; danh sách rỗng thì không chèn gì.

        Chỉ chèn, không cập nhật: evidence phải bất biến như snapshot, nếu không
        guardrail của lượt sau sẽ đối chiếu với số đã bị sửa.
        """

        if not facts:
            return
        now = self.clock.now()
        self.session.add_all(
            [
                RunEvidenceRow(
                    evidence_id=uuid4(),
                    run_id=run_id,
                    fact_code=fact.fact_code,
                    source_table=fact.source_table,
                    source_id=fact.source_id,
                    value_text=fact.value_text,
                    created_at=now,
                )
                for fact in facts
            ]
        )
        await self.session.flush()

    async def save_candidates(self, run_id: UUID, candidates: Sequence[CandidateInput]) -> None:
        """Chèn ứng viên của run; `rank` để trống vì thứ hạng chỉ có sau chấm điểm."""

        if not candidates:
            return
        now = self.clock.now()
        self.session.add_all(
            [
                RunCandidateRow(
                    id=uuid4(),
                    run_id=run_id,
                    vehicle_id=candidate.vehicle_id,
                    layer_reached=candidate.layer_reached,
                    rank=None,
                    over_budget_percent=None,
                    created_at=now,
                )
                for candidate in candidates
            ]
        )
        await self.session.flush()

    async def save_scores(self, run_id: UUID, scores: Sequence[ScoreInput]) -> None:
        """Chèn điểm; `reasons` giữ nguyên văn chuỗi đã render kèm trace `slot=`."""

        if not scores:
            return
        now = self.clock.now()
        self.session.add_all(
            [
                ScoringResultRow(
                    id=uuid4(),
                    run_id=run_id,
                    vehicle_id=score.vehicle_id,
                    score=score.score,
                    reasons=[{"reason": reason} for reason in score.reasons],
                    created_at=now,
                )
                for score in scores
            ]
        )
        await self.session.flush()

    async def set_candidate_ranks(self, run_id: UUID, ranks: Mapping[UUID, int]) -> None:
        """Điền thứ hạng cho đúng những xe được chọn; xe không chọn giữ `rank` rỗng."""

        for vehicle_id, rank in ranks.items():
            await self.session.execute(
                update(RunCandidateRow)
                .where(RunCandidateRow.run_id == run_id, RunCandidateRow.vehicle_id == vehicle_id)
                .values(rank=rank)
            )

    async def ranked_vehicle_ids(self, run_id: UUID) -> list[UUID]:
        """Return ranked candidates in the frozen recommendation order."""
        rows = await self.session.execute(
            select(RunCandidateRow.vehicle_id)
            .where(RunCandidateRow.run_id == run_id, RunCandidateRow.rank.is_not(None))
            .order_by(RunCandidateRow.rank)
        )
        return list(rows.scalars())

    async def save_tco_estimate(self, run_id: UUID, result: DetailedTcoResult) -> None:
        """Đóng băng TCO của một run; kết quả `TCO_UNAVAILABLE` thì không ghi gì.

        Ghi hàng toàn số 0 cho trường hợp thiếu dữ liệu là biến "chưa tính được"
        thành "chi phí bằng 0" — hai điều khác hẳn nhau (PRD mục 9).
        """

        if result.unavailable_reason is not None or result.total_vnd is None:
            return
        if result.assumptions_id is None or result.monthly_distance_km is None:
            return
        components = result.components_vnd
        self.session.add(
            TcoEstimateRow(
                id=uuid4(),
                run_id=run_id,
                vehicle_id=result.vehicle_id,
                assumption_id=result.assumptions_id,
                monthly_distance_km=result.monthly_distance_km,
                promoted_purchase_price_vnd=int(components["promoted_purchase_price_vnd"]),
                rolling_fees_vnd=int(components["rolling_fees_vnd"]),
                energy_vnd=int(components["energy_vnd"]),
                battery_vnd=int(components["battery_vnd"]),
                scheduled_maintenance_vnd=int(components["scheduled_maintenance_vnd"]),
                total_vnd=int(result.total_vnd),
                created_at=self.clock.now(),
            )
        )
        await self.session.flush()
