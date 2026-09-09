"""Document settings unit tests."""

import pytest
from pydantic import SecretStr, ValidationError

from src.document.infrastructure.settings import (
    ALLOWED_DOCUMENT_MIME_TYPES,
    DOCUMENT_MAX_FILE_SIZE_BYTES,
    PRESIGNED_DOWNLOAD_TTL_SECONDS,
    DocumentSettings,
)


class TestDocumentSettings:
    def test_disabled_settings_do_not_require_storage_or_database_credentials(self) -> None:
        # Given
        # When
        settings = DocumentSettings(_env_file=None, enabled=False)

        # Then
        assert settings.enabled is False
        assert settings.max_file_size_bytes == DOCUMENT_MAX_FILE_SIZE_BYTES
        assert settings.presigned_download_ttl_seconds == PRESIGNED_DOWNLOAD_TTL_SECONDS
        assert settings.allowed_mime_types == ALLOWED_DOCUMENT_MIME_TYPES

    def test_enabled_settings_require_storage_and_database_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Given / When / Then
        monkeypatch.delenv("DOCUMENT_DATABASE_URL", raising=False)
        with pytest.raises(ValidationError, match="database_url"):
            DocumentSettings(_env_file=None, enabled=True, database_url="")

    def test_enabled_settings_reject_public_bucket(self) -> None:
        # Given
        settings = _enabled_settings(bucket_private=False)

        # When / Then
        with pytest.raises(ValidationError, match="bucket_private"):
            DocumentSettings(_env_file=None, **settings)

    def test_accepts_text_csv_for_csv_uploads(self) -> None:
        # Given / When
        settings = DocumentSettings(_env_file=None, **_enabled_settings())

        # Then
        assert "text/csv" in settings.allowed_mime_types

    def test_fixed_upload_and_presign_contracts_cannot_be_overridden(self) -> None:
        # Given / When
        settings = DocumentSettings(
            _env_file=None,
            **_enabled_settings(),
            max_file_size_bytes=1,
            presigned_download_ttl_seconds=1,
        )

        # Then
        assert settings.max_file_size_bytes == DOCUMENT_MAX_FILE_SIZE_BYTES
        assert settings.presigned_download_ttl_seconds == PRESIGNED_DOWNLOAD_TTL_SECONDS

    def test_settings_hide_storage_credentials_from_representation(self) -> None:
        # Given / When
        settings = DocumentSettings(_env_file=None, **_enabled_settings())

        # Then
        rendered = repr(settings)
        assert settings.access_key.get_secret_value() not in rendered
        assert settings.secret_key.get_secret_value() not in rendered


def _enabled_settings(*, bucket_private: bool = True) -> dict[str, str | bool | SecretStr]:
    return {
        "enabled": True,
        "database_url": "postgresql+asyncpg://document_user:password@localhost:5432/document",
        "minio_endpoint": "http://localhost:9000",
        "bucket_name": "documents",
        "access_key": SecretStr("document-access-key"),
        "secret_key": SecretStr("document-secret-key"),
        "bucket_private": bucket_private,
    }
