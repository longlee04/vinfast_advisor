"""[A4-4] Composition dựng đủ service Khối 2 — thiếu một cái là node im lặng bỏ bước."""

from __future__ import annotations

import pytest

from src.agents.composition import AgentComposition
from src.agents.services.candidate_tuning import CatalogDifferentiator


async def _started() -> AgentComposition:
    composition = AgentComposition(
        # URL không trỏ tới DB nào: `create_async_engine` không mở kết nối cho tới
        # truy vấn đầu tiên, nên test này chỉ kiểm tra việc lắp ráp.
        database_url="postgresql+asyncpg://khong-ket-noi:x@127.0.0.1:1/khong-ket-noi"
    )
    await composition.start()
    return composition


@pytest.mark.asyncio
async def test_block_two_services_are_all_wired() -> None:
    composition = await _started()
    services = composition.services

    assert services.conversation is not None
    assert services.bottleneck_detector is not None
    assert services.slot_extraction is not None
    assert services.slot_planning is not None
    assert services.intent_routing is not None
    assert services.vehicle_overview is not None
    assert services.retrieval is not None
    assert services.snapshotting is not None
    assert services.recommendation is not None
    assert services.verification is not None
    assert services.candidate_tuning is not None
    await composition.shutdown()


@pytest.mark.asyncio
async def test_narrowing_uses_the_catalog_differentiator_not_the_canned_question() -> None:
    composition = await _started()

    tuning = composition.services.candidate_tuning

    assert isinstance(tuning.differentiator, CatalogDifferentiator)
    await composition.shutdown()


@pytest.mark.asyncio
async def test_an_empty_database_url_leaves_services_empty_without_raising() -> None:
    composition = AgentComposition(database_url="")

    await composition.start()

    assert composition.services.slot_extraction is None
    # Lõi v1 (LangGraph) đã xoá 2026-08-31: graph cố ý là None — xem chain.py.
    assert composition.graph is None
