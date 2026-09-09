"""Allowlisted HTTP adapter for manually triggered official policy ingestion."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx

from src.document.application.policy_sources import (
    FetchedPolicySource,
    PolicySourceFetchError,
    PolicySourceNotModified,
    validate_official_source_url,
)

MAX_POLICY_SOURCE_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 3
USER_AGENT = "P150-Policy-Inventory/1.0 (manual admin review)"


class HttpPolicySourceFetcher:
    """Fetch only reviewed HTTPS hosts with bounded redirects, retries, and size."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchedPolicySource | PolicySourceNotModified:
        """Fetch and hash bytes without importing or activating any policy."""
        validate_official_source_url(url)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html,text/plain,*/*"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=False)
        try:
            current_url = url
            for redirect_count in range(MAX_REDIRECTS + 1):
                response = await self._request_with_retry(client, current_url, headers)
                if response.status_code == httpx.codes.NOT_MODIFIED:
                    return PolicySourceNotModified(url, current_url)
                if response.is_redirect:
                    if redirect_count == MAX_REDIRECTS:
                        raise PolicySourceFetchError("policy source exceeded redirect limit")
                    location = response.headers.get("location")
                    if not location:
                        raise PolicySourceFetchError("policy redirect has no location")
                    current_url = urljoin(current_url, location)
                    validate_official_source_url(current_url)
                    continue
                if response.status_code != httpx.codes.OK:
                    raise PolicySourceFetchError("official policy source returned a non-success status")
                payload = response.content
                if len(payload) > MAX_POLICY_SOURCE_BYTES:
                    raise PolicySourceFetchError("policy source exceeds size limit")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
                _validate_payload(payload, content_type)
                return FetchedPolicySource(
                    requested_url=url,
                    canonical_url=current_url,
                    payload=payload,
                    content_type=content_type,
                    content_hash=hashlib.sha256(payload).hexdigest(),
                    retrieved_at=datetime.now(UTC),
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )
            raise PolicySourceFetchError("policy source redirect failed")
        finally:
            if owns_client:
                await client.aclose()

    async def _request_with_retry(
        self, client: httpx.AsyncClient, url: str, headers: dict[str, str]
    ) -> httpx.Response:
        last_error: httpx.RequestError | None = None
        for attempt in range(3):
            try:
                return await client.get(url, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = error
                if attempt < 2:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise PolicySourceFetchError("official policy source is unavailable") from last_error


def _validate_payload(payload: bytes, content_type: str) -> None:
    if not payload:
        raise PolicySourceFetchError("policy source is empty")
    if content_type == "application/pdf" and not payload.startswith(b"%PDF-"):
        raise PolicySourceFetchError("policy PDF magic bytes do not match")
    if content_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    } and not payload.startswith(b"PK"):
        raise PolicySourceFetchError("policy DOCX magic bytes do not match")
    if content_type == "text/html":
        prefix = payload[:2048].lstrip().casefold()
        if b"<html" not in prefix and b"<!doctype html" not in prefix:
            raise PolicySourceFetchError("policy HTML payload does not match its MIME type")
    if content_type not in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "text/html",
        "text/plain",
    }:
        raise PolicySourceFetchError("policy source MIME type is not supported")


__all__ = ["HttpPolicySourceFetcher", "PolicySourceNotModified"]
