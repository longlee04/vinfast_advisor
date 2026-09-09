"""Mục 4 prompt multi-slot: tran so lan hoi mot slot, ben vung qua cac luot."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from src.agents.chain import run_turn
from src.agents.domain.budget_parsing import NO_BUDGET_LIMIT_VND
from src.agents.domain.values import SlotName
from src.agents.services.slot_planning import MAX_ASK_ATTEMPTS


class _AlwaysAsksBudget:
    """Graph gia lap: luot nao cung hoi ngan sach va khach khong tra loi duoc."""

    def __init__(self) -> None:
        self.seen_ask_counts: list[dict[str, int]] = []

    async def ainvoke(self, state: dict) -> dict:
        self.seen_ask_counts.append(dict(state.get("ask_counts", {})))
        return {
            "slots": dict(state.get("slots", {})),
            "answer": None,
            "pending_question": "Anh/chi du tinh khoang bao nhieu ạ?",
            "pending_slot": SlotName.BUDGET_MAX_VND.value,
            "lookup_facts": [],
        }


@pytest.mark.asyncio
async def test_ask_count_survives_across_turns(
    agent_composition, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Dem phai nam o DB: moi luot la mot request rieng.

    Giu `retry_count` trong bo nho thi luot sau luon thay 0 va tran retry khong
    bao gio chan duoc gi.
    """

    graph = _AlwaysAsksBudget()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"

    for _ in range(3):
        await run_turn(
            graph,
            agent_composition.services,
            session_id=session_id,
            customer_id=customer_id,
            user_message="hmm",
        )

    counts = await agent_composition.services.ask_tracking.load_ask_counts(session_id)
    assert counts[SlotName.BUDGET_MAX_VND.value] == 3
    assert graph.seen_ask_counts[0] == {}
    assert graph.seen_ask_counts[1][SlotName.BUDGET_MAX_VND.value] == 1
    assert graph.seen_ask_counts[2][SlotName.BUDGET_MAX_VND.value] == 2


@pytest.mark.asyncio
async def test_field_past_the_cap_is_marked_open_and_the_flow_moves_on(
    agent_composition, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Qua tran → ghi gia tri "mo" that vao slot, khong chi bo qua khi chon cau hoi.

    `require_complete` va `build_criteria` doc slot tu DB; bo qua ma khong ghi
    thi luong tu van van chan o "thieu slot bat buoc".
    """

    graph = _AlwaysAsksBudget()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"

    for _ in range(MAX_ASK_ATTEMPTS + 2):
        await run_turn(
            graph,
            agent_composition.services,
            session_id=session_id,
            customer_id=customer_id,
            user_message="hmm",
        )

    slots = await agent_composition.services.conversation.load_slots(session_id, customer_id)
    assert slots[SlotName.BUDGET_MAX_VND.value] == NO_BUDGET_LIMIT_VND


class _AnswersBudgetOnce:
    """Khach tra loi duoc ngan sach o luot nay."""

    async def ainvoke(self, state: dict) -> dict:
        slots = dict(state.get("slots", {}))
        slots[SlotName.BUDGET_MAX_VND.value] = 700_000_000
        return {
            "slots": slots,
            "answer": None,
            "pending_question": "Anh/chi mua xe de dung vao viec gi ạ?",
            "pending_slot": SlotName.PURPOSE.value,
            "lookup_facts": [],
        }


@pytest.mark.asyncio
async def test_answering_a_field_resets_its_counter(
    agent_composition, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Lap duoc field thi dem ve 0 (prompt muc 4)."""

    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    # MAX_ASK_ATTEMPTS giờ là 1 (T6): một lượt hỏi budget trước, rồi khách trả lời.
    for _ in range(1):
        await run_turn(
            _AlwaysAsksBudget(),
            agent_composition.services,
            session_id=session_id,
            customer_id=customer_id,
            user_message="hmm",
        )

    await run_turn(
        _AnswersBudgetOnce(),
        agent_composition.services,
        session_id=session_id,
        customer_id=customer_id,
        user_message="700 trieu",
    )

    counts = await agent_composition.services.ask_tracking.load_ask_counts(session_id)
    assert counts[SlotName.BUDGET_MAX_VND.value] == 0
    assert counts[SlotName.PURPOSE.value] == 1
