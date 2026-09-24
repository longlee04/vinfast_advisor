"""Customer 360 service với repo/LLM giả: cờ tắt không làm gì, LLM hỏng → gắn tạm chờ TVV."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agents.domain.agent_flag import AgentFlagState
from src.agents.domain.buyer_for import BuyerFor
from src.agents.domain.opportunity_attach import AttachKind, OpportunityView
from src.agents.services.operations.customer_360 import (
    Customer360Operations,
    Customer360TurnHook,
    SessionContext,
)

NOW = datetime(2026, 9, 24, tzinfo=UTC)


class Flags:
    def __init__(self, *on: str) -> None:
        self.on = set(on)

    async def load(self, name: str) -> AgentFlagState | None:
        return AgentFlagState(name=name, enabled=name in self.on, rollout_percent=100)


class Scheduler:
    def __init__(self) -> None:
        self.labels: list[str] = []
        self.works: list = []

    def schedule(self, work, *, label: str) -> None:  # noqa: ANN001
        self.labels.append(label)
        self.works.append(work)


class SpyOperations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool | None]] = []

    async def refresh_session(self, session_id: str, *, force_extract: bool | None = None) -> None:
        self.calls.append((session_id, force_extract))


class Repo:
    def __init__(self, opportunities: list[OpportunityView]) -> None:
        self.opportunities = opportunities
        self.decisions = []

    async def load_session_context(self, session_id: str) -> SessionContext:
        return SessionContext(
            session_id=session_id,
            customer_id="c1",
            slots={"vehicle_type": "CAR", "passenger_count": 7},
            user_turns={1: "tư vấn xe"},
            turn_count=4,
            last_activity_at=NOW,
        )

    async def list_open_opportunities(self, customer_id: str) -> list[OpportunityView]:
        return self.opportunities

    async def apply_attachment(self, context, decision, buyer_for, at):  # noqa: ANN001, ANN201
        self.decisions.append(decision)
        return decision.target_id

    async def current_insights(self, customer_id: str) -> list:
        return []

    async def load_heat_inputs(self, opportunity_id: str, now: datetime) -> None:
        return None

    async def profile_needs_identity(self, customer_id: str) -> bool:
        return False


class BrokenClassifier:
    async def classify(self, summary, candidates):  # noqa: ANN001, ANN201
        raise RuntimeError("provider down")


@pytest.mark.asyncio
async def test_hook_moi_luot_gan_phien_trich_llm_theo_nhip() -> None:
    """Plan §21: MỖI lượt gắn phiên + ghi slot (tư vấn viên thấy ngay); trích LLM mỗi 4 lượt."""

    scheduler = Scheduler()
    operations = SpyOperations()
    off = Customer360TurnHook(operations, Flags(), scheduler)  # type: ignore[arg-type]
    on = Customer360TurnHook(operations, Flags("customer360_attach"), scheduler)  # type: ignore[arg-type]

    await off(session_id="s1", customer_id="c1", turn_count=4)
    await on(session_id="s1", customer_id="c1", turn_count=0)
    assert scheduler.labels == []
    await on(session_id="s1", customer_id="c1", turn_count=3)
    await on(session_id="s1", customer_id="c1", turn_count=8)
    assert scheduler.labels == ["customer360:s1", "customer360:s1"]
    for work in scheduler.works:
        await work()
    # Lượt 3: không trích LLM (ép False); lượt 8: để cờ `customer360_extractor` quyết (None).
    assert operations.calls == [("s1", False), ("s1", None)]


@pytest.mark.asyncio
async def test_llm_phan_loai_hong_thi_gan_tam_cho_tvv() -> None:
    existing = OpportunityView(
        opportunity_id="O1",
        vehicle_type="CAR",
        buyer_for=BuyerFor.SELF,
        slots={"vehicle_type": "CAR", "passenger_count": 4},
        status="OPEN",
        last_seen_at=NOW,
    )
    repo = Repo([existing])
    operations = Customer360Operations(repo, clock=lambda: NOW, classifier=BrokenClassifier())

    result = await operations.refresh_session("s1", force_extract=False)

    [decision] = repo.decisions
    assert result is not None and result.rule_code == "R7"
    assert (decision.kind, decision.target_id, decision.needs_review) == (AttachKind.UPDATE, "O1", True)
