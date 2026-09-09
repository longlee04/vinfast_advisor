"""A8-4 — role guard on the Admin API: only ADMIN gets through."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.api.notice_routes import router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.services.operations.notices import NoticeSummary
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
NOTICE_ID = uuid4()


class FakeNoticeOperations:
    """Fake implementing the use case surface the router depends on."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, str, str]] = []

    async def publish(self, title: str, content: str, priority: str, created_by: str) -> UUID:
        self.published.append((title, content, priority, created_by))
        return NOTICE_ID

    async def mark_read(self, notice_id: UUID, advisor_id: str) -> None:
        return None

    async def list_for(self, advisor_id: str) -> list[NoticeSummary]:
        return [
            NoticeSummary(
                notice_id=NOTICE_ID,
                title="Chinh sach moi",
                content="Noi dung",
                priority="NORMAL",
                created_at=NOW,
                read=False,
            )
        ]


@pytest.fixture
def operations() -> FakeNoticeOperations:
    return FakeNoticeOperations()


@pytest.fixture
def client(operations: FakeNoticeOperations) -> Iterator[TestClient]:
    from src.agents.api.notice_routes import notice_operations

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[notice_operations] = lambda: operations
    with TestClient(app) as test_client:
        yield test_client


def _sign_in(client: TestClient, role: Role, staff_id: str = "user-1") -> None:
    client.app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id=staff_id, role=role)


def _publish_payload() -> dict[str, str]:
    return {"title": "Chinh sach moi", "content": "Noi dung", "priority": "NORMAL"}


def test_customer_calling_the_admin_notice_api_is_forbidden(
    client: TestClient, operations: FakeNoticeOperations
) -> None:
    # Given
    _sign_in(client, Role.CUSTOMER)

    # When
    response = client.post("/agent/notices", json=_publish_payload())

    # Then
    assert response.status_code == 403
    assert operations.published == []


def test_advisor_calling_the_admin_notice_api_is_forbidden(
    client: TestClient, operations: FakeNoticeOperations
) -> None:
    # Given
    _sign_in(client, Role.ADVISOR)

    # When
    response = client.post("/agent/notices", json=_publish_payload())

    # Then
    assert response.status_code == 403
    assert operations.published == []


def test_admin_can_publish_a_notice(client: TestClient, operations: FakeNoticeOperations) -> None:
    # Given
    _sign_in(client, Role.ADMIN, staff_id="admin-1")

    # When
    response = client.post("/agent/notices", json=_publish_payload())

    # Then
    assert response.status_code == 201
    assert operations.published == [("Chinh sach moi", "Noi dung", "NORMAL", "admin-1")]


def test_advisor_can_mark_a_notice_as_read(client: TestClient) -> None:
    # Given — the guard blocks publishing, not reading
    _sign_in(client, Role.ADVISOR, staff_id="advisor-a")

    # When
    response = client.post(f"/agent/notices/{NOTICE_ID}/read")

    # Then
    assert response.status_code == 204


def test_customer_cannot_mark_a_notice_as_read(client: TestClient) -> None:
    # Given — negative case: notices are staff-only
    _sign_in(client, Role.CUSTOMER)

    # When
    response = client.post(f"/agent/notices/{NOTICE_ID}/read")

    # Then
    assert response.status_code == 403
