"""[A0-5] `AgentUnitOfWork` — transaction boundary thật trên Postgres (mục 6.4)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.models import ConversationSessionRow

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ADAPTERS_DIR = REPOSITORY_ROOT / "src" / "agents" / "adapters"


def _new_session_row(session_id) -> ConversationSessionRow:
    now = datetime.now(UTC)
    return ConversationSessionRow(
        session_id=session_id,
        customer_id="customer-uow-test",
        started_at=now,
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest_asyncio.fixture
async def unit_of_work(migrated_engine: AsyncEngine, clean_agent_database: None) -> AgentUnitOfWork:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    # Factory test: trả thẳng AsyncSession — bó repository thật (A0-5 chưa cần)
    # là việc của Khối 4 khi `adapters/repositories.py` tồn tại (mục docstring
    # `AgentUnitOfWork`); ở đây chỉ kiểm cơ chế mở/đóng transaction.
    return AgentUnitOfWork(session_factory, transaction_factory=lambda session: session)


@pytest.mark.asyncio
async def test_second_write_failing_rolls_back_the_first(unit_of_work: AgentUnitOfWork) -> None:
    first_id = uuid4()

    with pytest.raises(Exception):  # noqa: B017 - lỗi cố ý ở lệnh ghi thứ hai (trùng PK)
        async with unit_of_work.transaction() as session:
            session.add(_new_session_row(first_id))
            await session.flush()
            session.add(_new_session_row(first_id))  # trùng PK session_id → lỗi
            await session.flush()

    async with unit_of_work.transaction() as session:
        rows = (
            (await session.execute(select(ConversationSessionRow).where(ConversationSessionRow.session_id == first_id)))
            .scalars()
            .all()
        )
        assert rows == []  # lệnh ghi đầu cũng bị rollback theo


@pytest.mark.asyncio
async def test_committed_write_is_visible_from_a_different_session(unit_of_work: AgentUnitOfWork) -> None:
    session_id = uuid4()

    async with unit_of_work.transaction() as session:
        session.add(_new_session_row(session_id))

    async with unit_of_work.transaction() as other_session:
        row = await other_session.get(ConversationSessionRow, session_id)
        assert row is not None
        assert row.customer_id == "customer-uow-test"


def _imports_or_calls_begin(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "begin":
            return True
    return False


def test_no_agent_repository_opens_its_own_session() -> None:
    """`adapters/unit_of_work.py` là NƠI DUY NHẤT gọi `session.begin()` (mục 6.4).

    Chưa có `adapters/repositories.py` (Khối 4 sở hữu, chưa tới lượt) nên test
    này hiện vacuous — nhưng cưỡng chế thật ngay khi file đó xuất hiện.
    """
    offenders = [
        path.name
        for path in sorted(ADAPTERS_DIR.glob("*.py"))
        if path.name != "unit_of_work.py" and _imports_or_calls_begin(path)
    ]
    assert offenders == []
