from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

import pytest

from src.agents.chain import run_turn
from src.agents.domain.values import SlotValue
from src.agents.services.conversation_memory import StartedMemoryTurn
from src.agents.services.registry import AgentServices


class Graph:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.calls.append(state)
        return {**state, "pending_question": "Bạn muốn xem ngân sách nào?"}


class Conversation:
    async def open_session(self, session_id: str, customer_id: str) -> None:
        return None

    async def load_slots(self, session_id: str, customer_id: str) -> dict[str, SlotValue]:
        return {"vehicle_type": "CAR"}

    async def save_turn(self, session_id: str, customer_id: str, slots: Mapping[str, SlotValue]) -> None:
        return None


class Memory:
    def __init__(self, replayed: str | None = None) -> None:
        self.replayed = replayed
        self.started: list[dict[str, object]] = []
        self.completed: list[dict[str, object]] = []

    async def start_turn(self, **kwargs: object) -> StartedMemoryTurn:
        self.started.append(kwargs)
        return StartedMemoryTurn("MEMORY-CONTEXT", self.replayed)

    async def complete_turn(self, **kwargs: object) -> None:
        self.completed.append(kwargs)


@pytest.mark.asyncio
async def test_run_turn_passes_memory_to_graph_and_persists_delivered_question() -> None:
    graph = Graph()
    memory = Memory()
    client_turn_id = uuid4()
    services = AgentServices(conversation=Conversation(), memory=memory)

    result = await run_turn(
        graph,
        services,
        session_id=str(uuid4()),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Mẫu còn lại giá bao nhiêu?",
    )

    assert graph.calls[0]["conversation_context"] == "MEMORY-CONTEXT"
    assert result.pending_question == "Bạn muốn xem ngân sách nào?"
    assert memory.completed[0]["delivered_assistant"] == "Bạn muốn xem ngân sách nào?"
    assert memory.completed[0]["client_turn_id"] == client_turn_id


@pytest.mark.asyncio
async def test_completed_client_turn_replays_without_invoking_graph_or_completing_again() -> None:
    graph = Graph()
    memory = Memory(replayed="Câu trả lời đã giao trước đó")
    services = AgentServices(conversation=Conversation(), memory=memory)

    result = await run_turn(
        graph,
        services,
        session_id=str(uuid4()),
        customer_id="customer-1",
        client_turn_id=uuid4(),
        user_message="retry",
    )

    assert result.answer == "Câu trả lời đã giao trước đó"
    assert graph.calls == []
    assert memory.completed == []
