"""Khong luot nao duoc tra ve bong bong chat rong cho khach."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from src.agents.chain import run_turn


class _SilentGraph:
    """Nhanh lookup thuan tren phien chua co slot: graph khong noi gi ca."""

    async def ainvoke(self, state: dict) -> dict:
        return {"slots": {}, "answer": None, "pending_question": None, "lookup_facts": []}


@pytest.mark.asyncio
async def test_a_turn_never_returns_silence_to_the_customer(
    agent_composition, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """`ask_or_retrieve` co nhanh tra `pending_question=None`; neu tra cuu cung
    khong ra fact thi ca luot khong sinh chu nao.

    Test o muc node khong thay duoc loi nay: no chi lo ra o `run_turn`, diem
    thoat duy nhat cua mot luot.
    """

    result = await run_turn(
        _SilentGraph(),
        agent_composition.services,
        session_id=str(uuid4()),
        customer_id=f"customer-{uuid4()}",
        user_message="xe nao re nhat",
    )

    assert (result.answer or "").strip() or (result.pending_question or "").strip()


class _GuardrailBlockedGraph:
    """`GuardrailNode._terminal_update`: chan ban nhap bang `answer=""`."""

    async def ainvoke(self, state: dict) -> dict:
        return {
            "slots": {},
            "answer": "",
            "pending_question": None,
            "terminal_reason": "GUARDRAIL_FAILED_ADVISOR_HANDOFF",
            "lookup_facts": [],
        }


@pytest.mark.asyncio
async def test_guardrail_handoff_tells_the_customer_instead_of_going_silent(
    agent_composition, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Guardrail chan noi dung chua kiem chung la dung, nhung im lang thi khong.

    `answer` la chuoi RONG chu khong phai `None`, nen kiem tra `is None` van cho
    lot va khach nhan bong bong chat trong. Luot da terminal thi phai bao da
    chuyen tu van vien, khong duoc hoi them.
    """

    result = await run_turn(
        _GuardrailBlockedGraph(),
        agent_composition.services,
        session_id=str(uuid4()),
        customer_id=f"customer-{uuid4()}",
        user_message="khong co gi dac biet",
    )

    assert (result.answer or "").strip()
    assert result.pending_question is None
    # [T7c] Mã nội bộ `GUARDRAIL_FAILED_ADVISOR_HANDOFF` (graph vẫn đặt) được làm
    # mờ thành `ADVISOR_HANDOFF` ở biên công khai: khách cần biết đã chuyển người,
    # không cần biết cơ chế nào chặn. Mã gốc còn nguyên trong outcome dưới DB.
    assert result.terminal_reason == "ADVISOR_HANDOFF"
