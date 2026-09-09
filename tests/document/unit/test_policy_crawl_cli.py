"""Manual policy crawl CLI remains bounded and review-oriented."""

import pytest

from scripts.crawl_vinfast_policies import _run_bounded
from src.document.application.policy_sources import PolicySourceFetchError, PolicySourceSpec


@pytest.mark.asyncio
async def test_batch_reports_one_fetch_failure_without_aborting_other_sources() -> None:
    sources = [
        PolicySourceSpec(
            key="blocked_index",
            url="https://vinfastauto.com/vn_vi/thong-tin-bao-hanh",
            source_kind="HTML_INDEX",
            priority="P0",
        ),
        PolicySourceSpec(
            key="available_pdf",
            url="https://static-cms-prod.vinfastauto.com/warranty.pdf",
            source_kind="PDF",
            priority="P0",
        ),
    ]

    async def operation(source: PolicySourceSpec) -> dict[str, object]:
        if source.key == "blocked_index":
            raise PolicySourceFetchError("manual browser review required")
        return {"key": source.key, "status": "FETCHED_DRAFT_ONLY"}

    results = await _run_bounded(sources, operation, interval_seconds=0)

    assert results[0]["status"] == "FETCH_FAILED_REVIEW_REQUIRED"
    assert results[1] == {"key": "available_pdf", "status": "FETCHED_DRAFT_ONLY"}
