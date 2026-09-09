"""Official source registry and safe fetch validation."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.document.application.policy_sources import (
    FetchedPolicySource,
    ImportOfficialPolicySource,
    PolicySourceManifest,
    PolicySourceSpec,
    UnsafePolicySourceError,
    validate_official_source_url,
)
from src.document.application.ports import StoredObject
from src.document.domain.entities import Document


def test_only_reviewed_vinfast_hosts_are_allowed() -> None:
    validate_official_source_url("https://vinfastauto.com/vn_vi/thong-tin-bao-hanh")
    validate_official_source_url("https://static-cms-prod.vinfastauto.com/warranty.pdf")

    with pytest.raises(UnsafePolicySourceError):
        validate_official_source_url("http://vinfastauto.com/insecure")
    with pytest.raises(UnsafePolicySourceError):
        validate_official_source_url("https://vinfastauto.com.evil.example/warranty.pdf")


def test_checked_in_manifest_has_unique_keys_and_p0_old_new_sources() -> None:
    path = Path("data-p150/policy_sources/vinfast_official_sources.json")
    manifest = PolicySourceManifest.model_validate_json(path.read_text(encoding="utf-8"))

    assert len({item.key for item in manifest.sources}) == len(manifest.sources)
    keys = {item.key for item in manifest.sources}
    assert {"motorbike_lfp_5y", "motorbike_lfp_6y_from_2025_08", "motorbike_non_lfp_3y"} <= keys
    assert all(item.status == "DISCOVERED" for item in manifest.sources)


def test_checked_in_manifest_covers_current_warranty_and_battery_contract_inventory() -> None:
    path = Path("data-p150/policy_sources/vinfast_official_sources.json")
    manifest = PolicySourceManifest.model_validate_json(path.read_text(encoding="utf-8"))

    keys = {item.key for item in manifest.sources}
    assert {
        "vf3_warranty_v1_5",
        "vf5_warranty_v2_2",
        "vf6_warranty_v1_5",
        "vf8_warranty_v1_5",
        "vf9_warranty_v1_9",
        "lac_hong_900_lx_warranty_v1",
        "minio_green_warranty_v2_0",
        "nerio_green_warranty_v1_1",
        "herio_green_warranty_v1_2",
        "limo_green_warranty_v1_0",
        "ec_van_warranty_v2",
        "ebus_6b_warranty_v1",
        "ebus_8b_warranty",
        "ebus_10b_warranty",
        "mpv7_warranty_v1_0",
        "motorbike_battery_contract_max_2026_03",
        "motorbike_battery_contract_non_swap_2026_08",
        "motorbike_battery_contract_swap_2026_08",
    } <= keys


class MemoryDocuments:
    def __init__(self) -> None:
        self.items: list[Document] = []

    async def add(self, document: Document) -> Document:
        self.items.append(document)
        return document

    async def get_by_source_hash(self, source_url: str, content_hash: str) -> Document | None:
        return next(
            (item for item in self.items if item.source_url == source_url and item.content_hash == content_hash),
            None,
        )

    async def get_latest_by_source_url(self, source_url: str) -> Document | None:
        return next((item for item in reversed(self.items) if item.source_url == source_url), None)


class MemoryUnitOfWork:
    def __init__(self, documents: MemoryDocuments) -> None:
        self.documents = documents

    @asynccontextmanager
    async def transaction(self):  # noqa: ANN202
        yield SimpleNamespace(documents=self.documents)


class MemoryStorage:
    def __init__(self) -> None:
        self.filenames: list[str] = []

    async def upload(
        self, document_id, data: BytesIO, filename: str, content_type: str  # noqa: ANN001
    ) -> StoredObject:
        del document_id
        self.filenames.append(filename)
        payload = data.read()
        import hashlib

        return StoredObject("policy/object", hashlib.sha256(payload).hexdigest(), content_type, len(payload))

    async def remove(self, object_key: str) -> None:
        del object_key


class StaticFetcher:
    def __init__(self, fetched: FetchedPolicySource) -> None:
        self.fetched = fetched
        self.calls = 0

    async def fetch(self, url: str, **kwargs):  # noqa: ANN003, ANN202
        del url, kwargs
        self.calls += 1
        return self.fetched


@pytest.mark.asyncio
async def test_same_source_hash_is_idempotent_and_changed_hash_creates_revision() -> None:
    import hashlib

    documents = MemoryDocuments()
    spec = PolicySourceSpec(
        key="vf5_test",
        url="https://static-cms-prod.vinfastauto.com/vf5.pdf",
        source_kind="PDF",
        priority="P0",
    )

    def fetched(payload: bytes) -> FetchedPolicySource:
        return FetchedPolicySource(
            requested_url=spec.url,
            canonical_url=spec.url,
            payload=payload,
            content_type="application/pdf",
            content_hash=hashlib.sha256(payload).hexdigest(),
            retrieved_at=datetime(2026, 8, 31, tzinfo=UTC),
        )

    first_use_case = ImportOfficialPolicySource(
        documents, MemoryUnitOfWork(documents), MemoryStorage(), StaticFetcher(fetched(b"%PDF-old"))
    )
    first = await first_use_case.execute(spec, "admin-1")
    duplicate = await first_use_case.execute(spec, "admin-1")
    newer = await ImportOfficialPolicySource(
        documents, MemoryUnitOfWork(documents), MemoryStorage(), StaticFetcher(fetched(b"%PDF-new"))
    ).execute(spec, "admin-1")

    assert duplicate.id == first.id
    assert len(documents.items) == 2
    assert newer.supersedes_document_id == first.id.value


@pytest.mark.asyncio
async def test_html_index_without_url_extension_is_stored_as_analyzable_html() -> None:
    import hashlib

    documents = MemoryDocuments()
    storage = MemoryStorage()
    url = "https://vinfastauto.com/vn_vi/thong-tin-bao-hanh"
    payload = b"<!doctype html><html><body>Warranty</body></html>"
    spec = PolicySourceSpec(
        key="warranty_index",
        url=url,
        source_kind="HTML_INDEX",
        priority="P0",
    )
    fetched = FetchedPolicySource(
        requested_url=url,
        canonical_url=url,
        payload=payload,
        content_type="text/html",
        content_hash=hashlib.sha256(payload).hexdigest(),
        retrieved_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    document = await ImportOfficialPolicySource(
        documents,
        MemoryUnitOfWork(documents),
        storage,
        StaticFetcher(fetched),
    ).execute(spec, "admin-1")

    assert storage.filenames == ["thong-tin-bao-hanh.html"]
    assert document.content_type == "text/html"
