"""Đọc/ghi `conversation_core_state` (spec mục 4). Một hàng/phiên, upsert."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.core.state import CoreState, Intent, Pending, PendingKind, Stage
from src.agents.domain.values import SlotName
from src.agents.models import ConversationCoreStateRow

_SLOT_BY_VALUE = {s.value: s for s in SlotName}


def to_row_values(state: CoreState) -> dict:
    return {
        "session_id": UUID(state.session_id),
        "stage": state.stage.value,
        "intent": state.intent.value,
        "slots": {k.value: v for k, v in state.slots.items()},
        "pending": None
        if state.pending is None
        else {
            "kind": state.pending.kind.value,
            "key": state.pending.key,
            "options": list(state.pending.options),
            "labels": list(state.pending.labels),
            "asked_at_turn": state.pending.asked_at_turn,
            "job": state.pending.job,
        },
        "chosen_vehicle_id": UUID(state.chosen_vehicle_id) if state.chosen_vehicle_id else None,
        "recommended_ids": list(state.recommended_ids),
        "ask_counts": dict(state.ask_counts),
        "turn_count": state.turn_count,
        "booking_id": UUID(state.booking_id) if state.booking_id else None,
    }


def from_row(row: ConversationCoreStateRow) -> CoreState:
    slots = {_SLOT_BY_VALUE[k]: v for k, v in (row.slots or {}).items() if k in _SLOT_BY_VALUE}
    pending = None
    if row.pending:
        kind = row.pending.get("kind")
        key = row.pending.get("key")
        if kind is None or key is None:
            raise ValueError(f"conversation_core_state.pending thiếu 'kind' hoặc 'key': {row.pending!r}")
        pending = Pending(
            kind=PendingKind(kind),
            key=key,
            options=tuple(row.pending.get("options") or ()),
            # Hàng cũ (ghi trước khi có `labels`) không có khoá này — mặc định rỗng,
            # cột JSONB không cần migration.
            labels=tuple(row.pending.get("labels") or ()),
            asked_at_turn=int(row.pending.get("asked_at_turn") or 0),
            # Hàng cũ không có khoá này — JSONB, không cần migration.
            job=str(row.pending.get("job") or ""),
        )
    return CoreState(
        session_id=str(row.session_id),
        stage=Stage(row.stage),
        intent=Intent(row.intent),
        slots=slots,
        pending=pending,
        chosen_vehicle_id=str(row.chosen_vehicle_id) if row.chosen_vehicle_id else None,
        recommended_ids=tuple(row.recommended_ids or ()),
        ask_counts=dict(row.ask_counts or {}),
        turn_count=int(row.turn_count or 0),
        # `getattr`: hàng đọc qua model cũ (trước agent_0033) không có cột này.
        booking_id=str(row.booking_id) if getattr(row, "booking_id", None) else None,
    )


@dataclass(slots=True)
class CoreStateRepository:
    session: AsyncSession

    async def load(self, session_id: str) -> CoreState | None:
        row = await self.session.get(ConversationCoreStateRow, UUID(session_id))
        return from_row(row) if row is not None else None

    async def exists(self, session_id: str) -> bool:
        stmt = select(ConversationCoreStateRow.session_id).where(
            ConversationCoreStateRow.session_id == UUID(session_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def save(self, state: CoreState) -> None:
        values = to_row_values(state)
        # `func.now()` là hằng số trong SUỐT một transaction (transaction
        # timestamp) — hai lần `save()` liên tiếp trong cùng transaction sẽ ra
        # cùng một `updated_at`. Dùng `clock_timestamp()` (đồng hồ tường, đổi
        # mỗi lần gọi) để cột này thật sự tiến lên mỗi lần ghi, cho
        # `ix_conversation_core_state_updated` có ý nghĩa.
        now = func.clock_timestamp()
        stmt = insert(ConversationCoreStateRow).values(**values, updated_at=now)
        update_cols = {k: stmt.excluded[k] for k in values if k != "session_id"}
        update_cols["updated_at"] = now
        await self.session.execute(stmt.on_conflict_do_update(index_elements=["session_id"], set_=update_cols))
        await self.session.flush()
