"""Luot dau tien cua mot phien moi phai tu mo phien cho dung chu so huu.

App that khong co endpoint nao tao `conversation_sessions`: khach gui thang
`session_id` moi vao `POST /agent/turn`. Neu `run_turn` khong mo phien truoc khi
doc slot, luot dau luon vo o `SessionOwnershipError`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.chain import run_turn
from src.agents.errors import SessionOwnershipError
from src.agents.models import ConversationSessionRow


class _StubGraph:
    """Thay cho graph that: luot nay chi kiem tra phan mo phien."""

    async def ainvoke(self, state: dict) -> dict:
        return {"slots": {}, "answer": "xong", "pending_question": None, "lookup_facts": []}


@pytest.mark.asyncio
async def test_first_turn_of_a_new_session_opens_it_for_its_owner(
    agent_composition, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"

    # When
    result = await run_turn(
        _StubGraph(),
        agent_composition.services,
        session_id=session_id,
        customer_id=customer_id,
        user_message="Toi can xe dien 5 cho",
    )

    # Then
    assert result.session_id == session_id
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session:
        owner = await session.scalar(
            select(ConversationSessionRow.customer_id).where(ConversationSessionRow.session_id == session_id)
        )
    assert owner == customer_id


@pytest.mark.asyncio
async def test_a_second_customer_cannot_take_over_someone_elses_session(
    agent_composition, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id = str(uuid4())
    await run_turn(
        _StubGraph(),
        agent_composition.services,
        session_id=session_id,
        customer_id="customer-chu-so-huu",
        user_message="Toi can xe dien 5 cho",
    )

    # When / Then
    with pytest.raises(SessionOwnershipError):
        await run_turn(
            _StubGraph(),
            agent_composition.services,
            session_id=session_id,
            customer_id="customer-nguoi-la",
            user_message="Cho toi xem phien nay",
        )
