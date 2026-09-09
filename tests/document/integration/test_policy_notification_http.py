"""HTTP authorization and safe response contracts for policy notifications."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.domain.authorization import Role
from src.document.application.errors import DocumentTextUnavailableError
from src.document.domain.policy_notifications import (
    PolicyEvidence,
    PolicyFact,
    PolicyNotification,
    PolicyNotificationConflictError,
    PolicyNotificationId,
    PolicyTopic,
    PolicyType,
)
from src.document.domain.values import DocumentId
from src.document.presentation.dependencies import CurrentPrincipal, get_current_principal
from src.document.presentation.policy_routes import (
    PolicyNotificationRouteServices,
    build_policy_notification_router,
)


def _draft() -> PolicyNotification:
    return PolicyNotification.create_draft(
        source_document_id=DocumentId("00000000-0000-0000-0000-000000000001"),
        policy_type=PolicyType.WARRANTY_POLICY,
        topic=PolicyTopic.BATTERY_WARRANTY,
        secondary_topics=(),
        affected_models=("VF7",),
        effective_from=date(2026, 9, 1),
        effective_to=None,
        facts=(PolicyFact("Thời hạn", "8 năm", "Pin VF7 được bảo hành 8 năm."),),
        evidence=(PolicyEvidence("Pin VF7 được bảo hành 8 năm.", "3.2"),),
        ai_confidence=0.96,
        title="Bản nháp AI",
        content="Nội dung bản nháp AI",
        actor_id="admin-1",
    )


class Workflow:
    def __init__(self) -> None:
        self.notification = _draft()
        self.analysis_error: Exception | None = None
        self.publish_error: Exception | None = None

    async def analyze(self, document_id: DocumentId, actor_id: str) -> PolicyNotification:
        assert document_id.value and actor_id
        if self.analysis_error is not None:
            raise self.analysis_error
        return self.notification

    async def update(
        self,
        notification_id: PolicyNotificationId,
        *,
        actor_id: str,
        title: str,
        content: str,
    ) -> PolicyNotification:
        assert notification_id == self.notification.id and actor_id
        self.notification = self.notification.edit(title=title, content=content)
        return self.notification

    async def publish(
        self,
        notification_id: PolicyNotificationId,
        actor_id: str,
        resolution: object | None = None,
    ) -> PolicyNotification:
        assert notification_id == self.notification.id
        del resolution
        if self.publish_error is not None:
            raise self.publish_error
        self.notification = self.notification.publish(actor_id)
        return self.notification

    async def list_published(self, *, page: int, page_size: int) -> tuple[PolicyNotification, ...]:
        assert page == 1 and page_size == 20
        return (self.notification,) if self.notification.published_at else ()


class ExecuteAdapter:
    def __init__(self, operation) -> None:  # noqa: ANN001
        self._operation = operation

    async def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        return await self._operation(*args, **kwargs)


@pytest.fixture
def app() -> tuple[FastAPI, Workflow]:
    workflow = Workflow()
    services = PolicyNotificationRouteServices(
        analyze=ExecuteAdapter(workflow.analyze),  # type: ignore[arg-type]
        update=ExecuteAdapter(workflow.update),  # type: ignore[arg-type]
        publish=ExecuteAdapter(workflow.publish),  # type: ignore[arg-type]
        list_published=ExecuteAdapter(workflow.list_published),  # type: ignore[arg-type]
    )
    application = FastAPI()
    application.include_router(build_policy_notification_router(services), prefix="/api/v1")
    return application, workflow


async def _request(application: FastAPI, method: str, path: str, **kwargs: object):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_customer_cannot_analyze_edit_or_publish(app: tuple[FastAPI, Workflow]) -> None:
    application, workflow = app

    async def customer() -> CurrentPrincipal:
        return CurrentPrincipal("customer-1", Role.CUSTOMER)

    application.dependency_overrides[get_current_principal] = customer
    source_id = workflow.notification.source_document_id.value
    notification_id = workflow.notification.id.value

    analyzed = await _request(application, "POST", f"/api/v1/documents/{source_id}/analyze-policy")
    edited = await _request(
        application,
        "PATCH",
        f"/api/v1/policy-notifications/{notification_id}",
        json={"title": "x", "content": "y"},
    )
    published = await _request(
        application,
        "POST",
        f"/api/v1/policy-notifications/{notification_id}/publish",
    )

    assert (analyzed.status_code, edited.status_code, published.status_code) == (403, 403, 403)


@pytest.mark.asyncio
async def test_admin_edits_publishes_and_customer_receives_only_safe_copy(
    app: tuple[FastAPI, Workflow],
) -> None:
    application, workflow = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin-1", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    source_id = workflow.notification.source_document_id.value
    analyzed = await _request(application, "POST", f"/api/v1/documents/{source_id}/analyze-policy")
    notification_id = analyzed.json()["id"]
    edited = await _request(
        application,
        "PATCH",
        f"/api/v1/policy-notifications/{notification_id}",
        json={"title": "Admin đã duyệt", "content": "Nội dung do Admin chỉnh sửa."},
    )
    published = await _request(
        application,
        "POST",
        f"/api/v1/policy-notifications/{notification_id}/publish",
    )

    async def customer() -> CurrentPrincipal:
        return CurrentPrincipal("customer-1", Role.CUSTOMER)

    application.dependency_overrides[get_current_principal] = customer
    listed = await _request(application, "GET", "/api/v1/notifications")
    item = listed.json()["items"][0]

    assert analyzed.status_code == 201
    assert edited.status_code == 200 and published.json()["status"] == "published"
    assert listed.status_code == 200
    assert item["title"] == "Admin đã duyệt"
    assert "ai_confidence" not in item and "facts" not in item
    assert item["source_document_id"] == source_id


@pytest.mark.asyncio
async def test_empty_or_scanned_policy_document_returns_stable_422(
    app: tuple[FastAPI, Workflow],
) -> None:
    application, workflow = app
    workflow.analysis_error = DocumentTextUnavailableError()

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin-1", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    response = await _request(
        application,
        "POST",
        f"/api/v1/documents/{workflow.notification.source_document_id.value}/analyze-policy",
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Document does not contain extractable text; OCR is not supported in this MVP."
    }


@pytest.mark.asyncio
async def test_overlapping_revision_returns_structured_409_without_publication(
    app: tuple[FastAPI, Workflow],
) -> None:
    application, workflow = app
    workflow.publish_error = PolicyNotificationConflictError("internal overlap details")

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin-1", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    response = await _request(
        application,
        "POST",
        f"/api/v1/policy-notifications/{workflow.notification.id.value}/publish",
        json={"resolution": "SUPERSEDE_DEFAULT"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "POLICY_SCOPE_CONFLICT",
            "message": "Phạm vi phiên bản đang chồng lấn; hãy sửa cohort trước khi publish.",
        }
    }
    assert workflow.notification.status.value == "draft"
