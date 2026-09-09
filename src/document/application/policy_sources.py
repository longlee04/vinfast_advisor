"""Contracts and validation for importing versioned official policy sources."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from io import BytesIO
from typing import Literal, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.document.application.ports import DocumentRepository, DocumentUnitOfWork, ObjectStorage
from src.document.domain.entities import Document, DocumentMetadata
from src.document.domain.values import SourceAuthority

OFFICIAL_POLICY_HOSTS = frozenset(
    {
        "vinfastauto.com",
        "www.vinfastauto.com",
        "static-cms-prod.vinfastauto.com",
    }
)


class UnsafePolicySourceError(ValueError):
    """Raised before any request to an untrusted or malformed source URL."""


class PolicySourceFetchError(RuntimeError):
    """Raised when an official source cannot be fetched within safety limits."""


class PolicySourceSpec(BaseModel):
    """One reviewed source inventory item; it is not automatically published."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(pattern=r"^[a-z0-9_]+$")
    url: str
    source_kind: Literal["HTML_INDEX", "PDF", "HTML_SECTION"]
    priority: Literal["P0", "P1", "P2"]
    expected_topics: list[str] = Field(default_factory=list)
    expected_models: list[str] = Field(default_factory=list)
    cadence: Literal["MANUAL", "DAILY", "WEEKLY", "MONTHLY"] = "MANUAL"
    status: Literal["DISCOVERED", "DRAFT", "ACTIVE", "NEEDS_OCR"] = "DISCOVERED"

    @model_validator(mode="after")
    def validate_url(self) -> PolicySourceSpec:
        validate_official_source_url(self.url)
        return self


class PolicySourceManifest(BaseModel):
    """Versioned registry loaded by the crawl CLI."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: int = Field(ge=1)
    sources: list[PolicySourceSpec]

    @model_validator(mode="after")
    def require_unique_keys(self) -> PolicySourceManifest:
        keys = [item.key for item in self.sources]
        if len(set(keys)) != len(keys):
            raise ValueError("policy source keys must be unique")
        return self


class FetchedPolicySource(BaseModel):
    """Verified bytes and HTTP revision metadata returned by a fetch adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    requested_url: str
    canonical_url: str
    payload: bytes
    content_type: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    retrieved_at: datetime
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class PolicySourceNotModified:
    """Conditional request result that must not create a new revision."""

    requested_url: str
    canonical_url: str


class PolicySourceFetcher(Protocol):
    """External HTTP boundary used only by an explicit import workflow."""

    async def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchedPolicySource | PolicySourceNotModified: ...


@dataclass(frozen=True, slots=True)
class ImportOfficialPolicySource:
    """Import a verified revision as DRAFT; never analyze or activate it automatically."""

    documents: DocumentRepository
    uow: DocumentUnitOfWork
    storage: ObjectStorage
    fetcher: PolicySourceFetcher

    async def execute(self, spec: PolicySourceSpec, actor_id: str) -> Document:
        existing_latest = await self.documents.get_latest_by_source_url(spec.url)
        fetched = await self.fetcher.fetch(
            spec.url,
            etag=existing_latest.source_etag if existing_latest else None,
            last_modified=existing_latest.source_last_modified if existing_latest else None,
        )
        if isinstance(fetched, PolicySourceNotModified):
            if existing_latest is None:
                raise PolicySourceFetchError("source returned 304 without a stored revision")
            return existing_latest
        existing = await self.documents.get_by_source_hash(
            fetched.canonical_url, fetched.content_hash
        )
        if existing is not None:
            return existing

        provisional = Document.create(
            DocumentMetadata(
                title=spec.key.replace("_", " ").title(),
                content_hash="",
                document_type="policy",
                source_url=fetched.canonical_url,
                source_authority=SourceAuthority.OFFICIAL,
                source_revision=fetched.content_hash[:12],
                source_retrieved_at=fetched.retrieved_at,
                source_etag=fetched.etag,
                source_last_modified=fetched.last_modified,
                supersedes_document_id=existing_latest.id.value if existing_latest else None,
            ),
            actor_id,
        )
        filename = _source_filename(spec, fetched)
        stored = await self.storage.upload(
            provisional.id,
            BytesIO(fetched.payload),
            filename,
            fetched.content_type,
        )
        if stored.content_hash != fetched.content_hash:
            await self.storage.remove(stored.object_key)
            raise PolicySourceFetchError("stored policy hash differs from fetched source")
        document = replace(
            provisional,
            content_hash=stored.content_hash,
            original_filename=filename,
            object_key=stored.object_key,
            content_type=stored.content_type,
            byte_size=stored.byte_size,
        )
        async with self.uow.transaction() as repositories:
            return await repositories.documents.add(document)


def validate_official_source_url(url: str) -> None:
    """Fail closed for non-HTTPS URLs, credentials, ports, or non-allowlisted hosts."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or host not in OFFICIAL_POLICY_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise UnsafePolicySourceError("policy source URL is not allowlisted")


def _source_filename(spec: PolicySourceSpec, fetched: FetchedPolicySource) -> str:
    filename = fetched.canonical_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if fetched.content_type == "text/html" and not filename.casefold().endswith((".html", ".htm")):
        return f"{filename or spec.key}.html"
    return filename or f"{spec.key}.bin"


__all__ = [
    "FetchedPolicySource",
    "ImportOfficialPolicySource",
    "OFFICIAL_POLICY_HOSTS",
    "PolicySourceFetchError",
    "PolicySourceManifest",
    "PolicySourceNotModified",
    "PolicySourceSpec",
    "UnsafePolicySourceError",
    "validate_official_source_url",
]
