"""Typed Document feature configuration."""

from functools import lru_cache
from typing import Final
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DOCUMENT_MAX_FILE_SIZE_BYTES: Final[int] = 25 * 1024 * 1024
PRESIGNED_DOWNLOAD_TTL_SECONDS: Final[int] = 60
ALLOWED_DOCUMENT_MIME_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/html",
        "text/csv",
    }
)
REQUIRED_DATABASE_DRIVER: Final[str] = "postgresql+asyncpg"


class DocumentConfigurationError(ValueError):
    """Raised when enabled Document configuration is incomplete or unsafe."""


class DocumentSettings(BaseSettings):
    """Document configuration loaded from `DOCUMENT_*` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="DOCUMENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = False
    database_url: str = Field(default="", repr=False)
    minio_endpoint: str = ""
    bucket_name: str = ""
    access_key: SecretStr = Field(default=SecretStr(""), repr=False)
    secret_key: SecretStr = Field(default=SecretStr(""), repr=False)
    bucket_private: bool = True

    @classmethod
    def env_configurable_fields(cls) -> tuple[str, ...]:
        """Return field names configured through `DOCUMENT_*` variables."""
        return tuple(cls.model_fields)

    @property
    def max_file_size_bytes(self) -> int:
        """Return the immutable 25 MiB upload limit."""
        return DOCUMENT_MAX_FILE_SIZE_BYTES

    @property
    def allowed_mime_types(self) -> frozenset[str]:
        """Return the immutable allow-list for MVP document uploads."""
        return ALLOWED_DOCUMENT_MIME_TYPES

    @property
    def presigned_download_ttl_seconds(self) -> int:
        """Return the immutable 60-second presigned download TTL."""
        return PRESIGNED_DOWNLOAD_TTL_SECONDS

    @field_validator("minio_endpoint", "bucket_name")
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _validate_enabled_configuration(self) -> "DocumentSettings":
        if self.enabled:
            self._validate_database_url()
            self._validate_storage_configuration()
        return self

    def _validate_database_url(self) -> None:
        if not self.database_url:
            raise DocumentConfigurationError("database_url is required when Document is enabled")
        driver = self.database_url.split("://", 1)[0]
        if driver != REQUIRED_DATABASE_DRIVER:
            raise DocumentConfigurationError("database_url must use the postgresql+asyncpg driver")
        if "://" not in self.database_url or not urlsplit(self.database_url).hostname:
            raise DocumentConfigurationError("database_url is not a valid connection URL")

    def _validate_storage_configuration(self) -> None:
        if not self.minio_endpoint:
            raise DocumentConfigurationError("minio_endpoint is required when Document is enabled")
        endpoint = urlsplit(self.minio_endpoint)
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
            raise DocumentConfigurationError("minio_endpoint must be a valid http(s) URL")
        if not self.bucket_name:
            raise DocumentConfigurationError("bucket_name is required when Document is enabled")
        if not self.access_key.get_secret_value():
            raise DocumentConfigurationError("access_key is required when Document is enabled")
        if not self.secret_key.get_secret_value():
            raise DocumentConfigurationError("secret_key is required when Document is enabled")
        if not self.bucket_private:
            raise DocumentConfigurationError("bucket_private must be true; public Document buckets are forbidden")


@lru_cache
def get_document_settings() -> DocumentSettings:
    """Return process-cached Document feature settings."""
    return DocumentSettings()
