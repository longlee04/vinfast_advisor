"""HTTP source adapter safety behavior without real network calls."""

import httpx
import pytest

from src.document.application.policy_sources import PolicySourceFetchError, UnsafePolicySourceError
from src.document.infrastructure.http_policy_source import (
    HttpPolicySourceFetcher,
    PolicySourceNotModified,
)


@pytest.mark.asyncio
async def test_fetch_hashes_a_valid_official_pdf() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("P150-Policy-Inventory")
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-test")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetched = await HttpPolicySourceFetcher(client).fetch(
            "https://static-cms-prod.vinfastauto.com/test.pdf"
        )

    assert not isinstance(fetched, PolicySourceNotModified)
    assert len(fetched.content_hash) == 64


@pytest.mark.asyncio
async def test_redirect_outside_allowlist_fails_before_following_it() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/file.pdf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsafePolicySourceError):
            await HttpPolicySourceFetcher(client).fetch("https://vinfastauto.com/source")


@pytest.mark.asyncio
async def test_conditional_304_does_not_create_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["if-none-match"] == '"abc"'
        return httpx.Response(304)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await HttpPolicySourceFetcher(client).fetch(
            "https://vinfastauto.com/source", etag='"abc"'
        )

    assert isinstance(result, PolicySourceNotModified)


@pytest.mark.asyncio
async def test_mismatched_pdf_mime_is_rejected() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"not a pdf")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PolicySourceFetchError):
            await HttpPolicySourceFetcher(client).fetch(
                "https://static-cms-prod.vinfastauto.com/test.pdf"
            )
