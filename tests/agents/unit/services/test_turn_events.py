"""Broker su kien theo phien — dung nguoi nghe, dung phien."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from src.agents.services.operations.turn_events import (
    InMemoryTurnEventBroker,
    TurnEvent,
)


@pytest.mark.asyncio
async def test_subscriber_receives_event_of_its_own_session() -> None:
    broker = InMemoryTurnEventBroker()
    session_id = uuid4()
    event = TurnEvent(session_id=session_id, review_id=uuid4(), kind="approved")

    async with broker.subscribe(session_id) as stream:
        await broker.publish(event)
        received = await asyncio.wait_for(anext(stream), timeout=1)

    assert received == event


@pytest.mark.asyncio
async def test_subscriber_never_receives_another_session_event() -> None:
    broker = InMemoryTurnEventBroker()
    mine, other = uuid4(), uuid4()

    async with broker.subscribe(mine) as stream:
        await broker.publish(TurnEvent(session_id=other, review_id=uuid4(), kind="approved"))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(stream), timeout=0.2)


@pytest.mark.asyncio
async def test_two_subscribers_of_one_session_both_receive() -> None:
    broker = InMemoryTurnEventBroker()
    session_id = uuid4()
    event = TurnEvent(session_id=session_id, review_id=uuid4(), kind="approved")

    async with broker.subscribe(session_id) as first, broker.subscribe(session_id) as second:
        await broker.publish(event)

        assert await asyncio.wait_for(anext(first), timeout=1) == event
        assert await asyncio.wait_for(anext(second), timeout=1) == event


@pytest.mark.asyncio
async def test_publish_without_subscriber_does_not_raise() -> None:
    broker = InMemoryTurnEventBroker()

    await broker.publish(TurnEvent(session_id=uuid4(), review_id=uuid4(), kind="approved"))


@pytest.mark.asyncio
async def test_subscriber_queue_is_removed_after_context_exit() -> None:
    broker = InMemoryTurnEventBroker()
    session_id = uuid4()

    async with broker.subscribe(session_id):
        assert len(broker._subscribers[session_id]) == 1

    assert session_id not in broker._subscribers


@pytest.mark.asyncio
async def test_subscriber_queue_is_removed_when_consumer_is_cancelled() -> None:
    broker = InMemoryTurnEventBroker()
    session_id = uuid4()
    entered = asyncio.Event()

    async def consume() -> None:
        async with broker.subscribe(session_id) as stream:
            entered.set()
            await anext(stream)

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(entered.wait(), timeout=1)
    consumer.cancel()

    with pytest.raises(asyncio.CancelledError):
        await consumer

    assert session_id not in broker._subscribers
