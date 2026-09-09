"""Real PostgreSQL fixtures for Agent schema migration tests."""

import os
import re
import socket
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
AGENT_TEST_DATABASE_URL = os.environ.get("AGENT_DATABASE_URL", "").strip() or DEFAULT_TEST_DATABASE_URL
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TEST_DATABASE_PREFIX = "p150_agent_test_"
_MIGRATION_ENVIRONMENTS = (
    ("alembic-auth.ini", "AUTH_DATABASE_URL"),
    ("alembic-document.ini", "DOCUMENT_DATABASE_URL"),
    ("alembic-products.ini", "PRODUCT_DATABASE_URL"),
    ("alembic-agent.ini", "AGENT_DATABASE_URL"),
)


def _server_is_reachable(database_url: str) -> bool:
    parts = urlsplit(database_url)
    host = parts.hostname or "localhost"
    port = parts.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


def run_alembic(
    database_url: str | None, configuration: str, database_variable: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Run one isolated migration environment."""
    environment = os.environ.copy()
    if database_url is not None:
        environment[database_variable] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", configuration, *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _database_url_parts(database_url: str) -> SplitResult:
    return urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))


def _database_url_with_name(database_url: str, database_name: str) -> str:
    parts = _database_url_parts(database_url)
    replaced = urlunsplit((parts.scheme, parts.netloc, f"/{database_name}", parts.query, parts.fragment))
    return replaced.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _create_test_database() -> tuple[str, str]:
    parts = _database_url_parts(AGENT_TEST_DATABASE_URL)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    database_name = f"{_TEST_DATABASE_PREFIX}{uuid.uuid4().hex}"
    engine = create_async_engine(
        maintenance_url.replace("postgresql://", "postgresql+asyncpg://", 1),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}" TEMPLATE template0'))
    finally:
        await engine.dispose()
    return _database_url_with_name(AGENT_TEST_DATABASE_URL, database_name), database_name


async def _drop_test_database(database_name: str) -> None:
    parts = _database_url_parts(AGENT_TEST_DATABASE_URL)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    engine = create_async_engine(
        maintenance_url.replace("postgresql://", "postgresql+asyncpg://", 1),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'ALTER DATABASE "{database_name}" WITH ALLOW_CONNECTIONS false'))
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE "{database_name}"'))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def agent_database_url() -> AsyncIterator[str]:
    """Create and remove an isolated PostgreSQL database for Agent tests."""
    if not _server_is_reachable(AGENT_TEST_DATABASE_URL):
        pytest.skip("PostgreSQL is not reachable; start it with 'docker compose up -d postgres'")
    database_url, database_name = await _create_test_database()
    try:
        yield database_url
    finally:
        await _drop_test_database(database_name)


@pytest_asyncio.fixture(scope="session")
async def _agent_migrations_applied(agent_database_url: str) -> None:
    """Áp toàn bộ migration Agent đúng một lần cho cả session.

    Tách riêng khỏi việc dựng `AsyncEngine`: phần tốn chi phí là 5 tiến trình
    con `alembic upgrade` (mỗi lần phải khởi động Python và import cả app),
    không phải việc tạo engine (rẻ, lazy connect). Session-scoped ở đây là
    AN TOÀN vì fixture không giữ engine/connection nào sống qua nhiều event
    loop của từng test — chỉ chạy subprocess rồi kết thúc. `migrated_engine`
    bên dưới vẫn function-scoped, tự dựng engine mới cho đúng event loop của
    từng test, tránh lỗi asyncpg "another operation is in progress" khi một
    engine/connection pool bị tái sử dụng giữa các event loop khác nhau mà
    một fixture session-scoped thật sự nắm giữ.
    """
    for configuration, database_variable in _MIGRATION_ENVIRONMENTS:
        revision = "4d0cument0001" if configuration == "alembic-document.ini" else "head"
        completed = run_alembic(agent_database_url, configuration, database_variable, "upgrade", revision)
        assert completed.returncode == 0, completed.stderr
        if configuration == "alembic-products.ini":
            completed = run_alembic(
                agent_database_url, "alembic-document.ini", "DOCUMENT_DATABASE_URL", "upgrade", "head"
            )
            assert completed.returncode == 0, completed.stderr


@pytest_asyncio.fixture
async def migrated_engine(agent_database_url: str, _agent_migrations_applied: None) -> AsyncIterator[AsyncEngine]:
    """Expose a fresh engine, bound to schema đã migrate sẵn cho cả session."""
    engine = create_async_engine(agent_database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def agent_session(migrated_engine: AsyncEngine, clean_agent_database: None) -> AsyncIterator[AsyncSession]:
    """Expose one transaction for Agent integration assertions."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        yield session


@pytest_asyncio.fixture
async def agent_session_factory(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> async_sessionmaker[AsyncSession]:
    """Nguồn session độc lập cùng engine với `agent_session`, cho adapter tự mở/đóng session."""
    return async_sessionmaker(migrated_engine, expire_on_commit=False)


class _AllowAllModeration:
    """Keep integration tests deterministic and offline at moderation boundary."""

    async def is_blocked(self, *, user_message: str, canonical: object | None = None) -> bool:
        del canonical
        return False


class _DeterministicScopeClassifier:
    """Classify known cross-brand fixtures without paid provider calls."""

    async def classify_scope(self, *, prompt: str) -> str:
        return "OUT_OF_SCOPE" if "Toyota" in prompt else "IN_SCOPE"


@pytest_asyncio.fixture
async def agent_composition(agent_database_url: str, monkeypatch: pytest.MonkeyPatch):
    """Start AgentComposition against isolated integration database."""
    from src.agents import composition as composition_module

    monkeypatch.setattr(composition_module, "OpenAIModerationAdapter", _AllowAllModeration)
    monkeypatch.setattr(composition_module, "LlmScopeClassifier", lambda llm: _DeterministicScopeClassifier())
    composition = composition_module.AgentComposition(agent_database_url)
    await composition.start()
    yield composition
    await composition.shutdown()


@pytest_asyncio.fixture
async def clean_agent_database(migrated_engine: AsyncEngine) -> AsyncIterator[None]:
    """Remove Agent rows before and after each constraint test."""
    tables = (
        "notice_reads, internal_notices, test_drive_bookings, review_queue, "
        "tco_estimates, scoring_result, run_evidence, run_candidates, run_snapshots, "
        "agent_runs, out_of_scope_log, conversation_turn_bottlenecks, conversation_turn_outcomes, "
        "conversation_messages, conversation_core_state, turn_traces, "
        "conversation_summaries, pending_feature_mentions, conversation_slots, customer_profiles, "
        "conversation_sessions"
    )
    async with migrated_engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    try:
        yield
    finally:
        async with migrated_engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))


def expected_agent_head() -> str:
    """Revision cuối của chuỗi migration agent, ĐỌC TỪ FILE.

    Trước đây các test khoá cứng chuỗi "agent_0025". Hệ quả: mỗi migration mới
    làm đỏ bốn test không liên quan gì tới nội dung của nó, và người thêm
    migration phải sửa những assert nói về một revision khác. Điều đáng khoá là
    "chuỗi có ĐÚNG MỘT head", không phải "head tên là gì".
    """

    versions = Path(__file__).resolve().parents[3] / "migrations" / "agents" / "versions"
    revisions: dict[str, str | None] = {}
    for path in versions.glob("agent_*.py"):
        source = path.read_text(encoding="utf-8")
        revision = re.search(r'^revision: str = "([^"]+)"', source, re.M)
        down = re.search(r'^down_revision: str \| None = (?:"([^"]+)"|None)', source, re.M)
        if revision is None:
            continue
        revisions[revision.group(1)] = down.group(1) if down and down.group(1) else None
    parents = {down for down in revisions.values() if down is not None}
    heads = sorted(revision for revision in revisions if revision not in parents)
    assert len(heads) == 1, f"chuoi migration phai co dung mot head, dang co: {heads}"
    return heads[0]
