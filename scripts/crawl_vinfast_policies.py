"""Manual inventory/fetch/import CLI for allowlisted VinFast policy sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from src.document.application.policy_sources import (  # noqa: E402
    ImportOfficialPolicySource,
    PolicySourceFetchError,
    PolicySourceManifest,
    PolicySourceNotModified,
    PolicySourceSpec,
    UnsafePolicySourceError,
    validate_official_source_url,
)
from src.document.composition import DocumentComposition  # noqa: E402
from src.document.infrastructure.http_policy_source import HttpPolicySourceFetcher  # noqa: E402
from src.document.infrastructure.settings import DocumentSettings  # noqa: E402

DEFAULT_MANIFEST = Path("data-p150/policy_sources/vinfast_official_sources.json")


class _OfficialLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = next((value for key, value in attrs if key.casefold() == "href"), None)
        if not href:
            return
        candidate = urljoin(self.base_url, href)
        try:
            validate_official_source_url(candidate)
        except UnsafePolicySourceError:
            return
        self.links.add(candidate)


def _load_manifest(path: Path) -> PolicySourceManifest:
    return PolicySourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _select_sources(manifest: PolicySourceManifest, source_key: str | None) -> list[PolicySourceSpec]:
    selected = [item for item in manifest.sources if source_key is None or item.key == source_key]
    if not selected:
        raise SystemExit(f"Unknown source key: {source_key}")
    return selected


async def _fetch(source: PolicySourceSpec) -> dict[str, object]:
    result = await HttpPolicySourceFetcher().fetch(source.url)
    if isinstance(result, PolicySourceNotModified):
        return {"key": source.key, "status": "NOT_MODIFIED", "url": result.canonical_url}
    return {
        "key": source.key,
        "status": "FETCHED_DRAFT_ONLY",
        "url": result.canonical_url,
        "content_type": result.content_type,
        "byte_size": len(result.payload),
        "sha256": result.content_hash,
        "etag": result.etag,
        "last_modified": result.last_modified,
    }


async def _discover(source: PolicySourceSpec) -> dict[str, object]:
    result = await HttpPolicySourceFetcher().fetch(source.url)
    if isinstance(result, PolicySourceNotModified):
        return {"key": source.key, "links": [], "status": "NOT_MODIFIED"}
    if result.content_type != "text/html":
        return {"key": source.key, "links": [], "status": "NOT_HTML"}
    parser = _OfficialLinkParser(result.canonical_url)
    parser.feed(result.payload.decode("utf-8", errors="replace"))
    return {"key": source.key, "links": sorted(parser.links), "status": "DISCOVERED"}


async def _import(source: PolicySourceSpec, target_env: str, apply: bool) -> dict[str, object]:
    if not apply:
        preview = await _fetch(source)
        preview["status"] = "DRY_RUN_NOT_IMPORTED"
        return preview
    if target_env == "production":
        raise SystemExit("Production import is intentionally performed through reviewed Admin rollout, not this CLI.")
    settings = DocumentSettings()
    if not settings.enabled:
        raise SystemExit("DOCUMENT_ENABLED=true and isolated Document DB/MinIO settings are required")
    composition = DocumentComposition(settings)
    await composition.start()
    try:
        resources = composition.resources
        if resources is None:
            raise SystemExit("Document resources are unavailable")
        document = await ImportOfficialPolicySource(
            resources.repository,
            resources.unit_of_work,
            resources.storage,
            HttpPolicySourceFetcher(),
        ).execute(source, "policy-crawl-cli")
        return {
            "key": source.key,
            "status": "IMPORTED_DRAFT",
            "document_id": document.id.value,
            "source_revision": document.source_revision,
            "sha256": document.content_hash,
        }
    finally:
        await composition.shutdown()


async def _run_bounded(
    sources: list[PolicySourceSpec],
    operation: Callable[[PolicySourceSpec], Awaitable[dict[str, object]]],
    *,
    interval_seconds: float,
) -> list[dict[str, object]]:
    """Run reviewed sources sequentially and report one failure without losing the batch."""
    results: list[dict[str, object]] = []
    for index, source in enumerate(sources):
        try:
            results.append(await operation(source))
        except (UnsafePolicySourceError, PolicySourceFetchError) as error:
            results.append(
                {
                    "key": source.key,
                    "status": "FETCH_FAILED_REVIEW_REQUIRED",
                    "url": source.url,
                    "reason": str(error),
                }
            )
        if index < len(sources) - 1 and interval_seconds > 0:
            await asyncio.sleep(interval_seconds)
    return results


async def _run(args: argparse.Namespace) -> int:
    if args.interval_seconds < 0:
        raise SystemExit("--interval-seconds must be non-negative")
    manifest = _load_manifest(args.manifest)
    sources = _select_sources(manifest, args.source_key)
    if args.command == "status":
        results = [item.model_dump(mode="json") for item in sources]
    elif args.command == "discover":
        results = await _run_bounded(
            [item for item in sources if item.source_kind == "HTML_INDEX"],
            _discover,
            interval_seconds=args.interval_seconds,
        )
    elif args.command == "fetch":
        results = await _run_bounded(
            sources,
            _fetch,
            interval_seconds=args.interval_seconds,
        )
    else:
        results = await _run_bounded(
            sources,
            lambda item: _import(item, args.target_env, args.apply),
            interval_seconds=args.interval_seconds,
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "discover", "fetch", "import"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-key")
    parser.add_argument("--target-env", choices=("test", "dev", "production"), default="test")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=1.0,
        help="Delay between official-source requests; commands remain sequential.",
    )
    parser.add_argument("--apply", action="store_true", help="Persist as Document DRAFT; never activates it")
    return parser


def main() -> int:
    """Run the explicit command; importing never happens without --apply."""
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
