"""Document lifespan integration tests."""

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from src.document.composition import DocumentComposition
from src.document.infrastructure.settings import DocumentSettings
from src.document.presentation.routes import DocumentRouteServices, build_document_router
from src.main import app, lifespan


class _UnreachableServices:
    """Placeholder use cases; registration tests never dispatch a Document request."""


def _document_router():
    return build_document_router(
        DocumentRouteServices(
            create=_UnreachableServices(),
            list_documents=_UnreachableServices(),
            detail=_UnreachableServices(),
            archive=_UnreachableServices(),
            download=_UnreachableServices(),
        )
    )


class TestEnabledDocumentLifespan:
    @pytest.mark.asyncio
    async def test_startup_fails_before_yield_when_required_configuration_is_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given
        monkeypatch.delenv("DOCUMENT_DATABASE_URL", raising=False)

        def missing_configuration() -> DocumentSettings:
            return DocumentSettings(_env_file=None, enabled=True, database_url="")

        monkeypatch.setattr("src.main.get_document_settings", missing_configuration)
        application = FastAPI()

        # When / Then
        with pytest.raises(ValidationError, match="database_url"):
            async with lifespan(application):
                pytest.fail("lifespan yielded despite missing Document configuration")
        assert not hasattr(application.state, "document")

    @pytest.mark.asyncio
    async def test_startup_fails_before_yield_when_document_bucket_is_public(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given
        def public_bucket_configuration() -> DocumentSettings:
            return DocumentSettings(
                _env_file=None,
                enabled=True,
                database_url="postgresql+asyncpg://document_user:password@localhost:5432/document",
                minio_endpoint="http://localhost:9000",
                bucket_name="documents",
                access_key="document-access-key",
                secret_key="document-secret-key",
                bucket_private=False,
            )

        monkeypatch.setattr("src.main.get_document_settings", public_bucket_configuration)
        application = FastAPI()

        # When / Then
        with pytest.raises(ValidationError, match="bucket_private"):
            async with lifespan(application):
                pytest.fail("lifespan yielded despite a public Document bucket")
        assert not hasattr(application.state, "document")


def test_document_routes_are_registered_on_the_application_before_lifespan() -> None:
    # Given / When
    paths = app.openapi()["paths"]

    # Then
    assert "/api/v1/documents" in paths
    assert "/api/v1/documents/{document_id}" in paths


class TestDisabledDocumentLifespan:
    @pytest.mark.asyncio
    async def test_disabled_document_startup_creates_no_resources(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Given
        disabled = DocumentSettings(_env_file=None, enabled=False)
        monkeypatch.setattr("src.main.get_document_settings", lambda: disabled)
        application = FastAPI()

        # When
        async with lifespan(application):
            composition = application.state.document

        # Then
        assert isinstance(composition, DocumentComposition)
        assert composition.enabled is False
        assert composition.resources is None

    @pytest.mark.asyncio
    async def test_disabled_document_startup_does_not_initialize_auth_or_document_resources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given
        disabled = DocumentSettings(_env_file=None, enabled=False)
        monkeypatch.setattr("src.main.get_document_settings", lambda: disabled)
        application = FastAPI()

        # When
        async with lifespan(application):
            pass

        # Then
        assert application.state.document.resources is None
