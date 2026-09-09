"""Regression tests for static Document API registration."""

from fastapi.testclient import TestClient

from src.document.composition import DocumentComposition
from src.document.infrastructure.settings import DocumentSettings
from src.document.presentation.dependencies import CurrentPrincipal, get_current_principal
from src.main import _document_principal_from_auth, app


def test_document_routes_are_registered_before_startup() -> None:
    # Given
    paths = app.openapi()["paths"]

    # When / Then
    assert "/api/v1/documents" in paths
    assert "/api/v1/documents/{document_id}" in paths
    assert "/api/v1/documents/{document_id}/download" in paths
    assert "/api/v1/documents/{document_id}/archive" in paths
    assert "/api/v1/documents/{document_id}/analyze-policy" in paths
    assert "/api/v1/policy-notifications/{notification_id}" in paths
    assert "/api/v1/policy-notifications/{notification_id}/publish" in paths
    assert "/api/v1/notifications" in paths


def test_document_auth_seam_is_wired_before_agent_startup() -> None:
    assert app.dependency_overrides.get(get_current_principal) is _document_principal_from_auth


def test_document_request_returns_generic_503_when_service_is_disabled() -> None:
    # Given
    original_document = getattr(app.state, "document", None)
    original_principal = app.dependency_overrides.get(get_current_principal)
    app.state.document = DocumentComposition(
        DocumentSettings(
            enabled=False,
            database_url="postgresql+asyncpg://unused",
            minio_endpoint="http://unused",
            bucket_name="unused",
            access_key="unused",
            secret_key="unused",
        )
    )

    async def principal() -> CurrentPrincipal:
        return CurrentPrincipal(actor_id="admin", role="admin")

    app.dependency_overrides[get_current_principal] = principal

    try:
        # When
        with TestClient(app) as client:
            response = client.get("/api/v1/documents")

        # Then
        assert response.status_code == 503
        assert response.json() == {"detail": "Document service unavailable"}
    finally:
        if original_principal is None:
            app.dependency_overrides.pop(get_current_principal, None)
        else:
            app.dependency_overrides[get_current_principal] = original_principal
        if original_document is not None:
            app.state.document = original_document
        else:
            del app.state.document
