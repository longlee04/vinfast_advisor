"""Hop dong port VehicleDocumentRepository + mapper row <-> entity."""

from __future__ import annotations

from datetime import UTC, datetime

from src.document.domain.entities import VehicleDocument
from src.document.domain.values import VehicleDocumentStatus
from src.document.infrastructure.repositories import (
    _vehicle_document_to_entity,
    _vehicle_document_to_row_values,
)


def _chunk(document_id: str = "d-1", chunk_index: int = 0) -> VehicleDocument:
    created = datetime(2026, 8, 6, tzinfo=UTC)
    updated = datetime(2026, 8, 7, tzinfo=UTC)
    return VehicleDocument(
        document_id=document_id,
        document_type="BROCHURE",
        title="VF 8 brochure",
        content="Xe co cua so troi toan canh.",
        chunk_index=chunk_index,
        status=VehicleDocumentStatus.DRAFT,
        created_at=created,
        updated_at=updated,
        vehicle_id="v-1",
        # Moi field optional duoi day duoc gan gia tri rieng, khac None va
        # khac nhau tung doi mot — de test round-trip bat duoc bug hoan doi
        # field (vd embedding_model <-> embedding_version) ma "None == None"
        # se khong bao gio phat hien ra.
        source_document_id="src-doc-1",
        source_content_hash="abc123",
        source_revision="rev-3",
        section_title="Trang bi",
        page_number=3,
        source_url="https://example.com/vf8-brochure.pdf",
        embedding_model="text-embedding-3-large",
        embedding_version="v2",
        valid_from=datetime(2026, 8, 1, tzinfo=UTC),
        valid_to=datetime(2026, 12, 31, tzinfo=UTC),
        created_by="user-created-1",
        approved_by="user-approved-2",
        approved_at=datetime(2026, 8, 5, tzinfo=UTC),
    )


def test_row_values_keep_every_populated_field() -> None:
    values = _vehicle_document_to_row_values(_chunk())

    assert values["document_id"] == "d-1"
    assert values["vehicle_id"] == "v-1"
    assert values["status"] == "DRAFT"
    assert values["chunk_index"] == 0
    assert values["page_number"] == 3
    assert values["source_content_hash"] == "abc123"
    assert values["section_title"] == "Trang bi"


def test_row_values_never_include_computed_content_tsv() -> None:
    # content_tsv la GENERATED column — ghi vao se lam INSERT that bai.
    values = _vehicle_document_to_row_values(_chunk())
    assert "content_tsv" not in values


def test_entity_round_trips_through_row_values() -> None:
    original = _chunk()

    class _Row:
        pass

    row = _Row()
    for key, value in _vehicle_document_to_row_values(original).items():
        setattr(row, key, value)
    for optional in (
        "source_document_id",
        "source_revision",
        "source_url",
        "embedding_model",
        "embedding_version",
        "valid_from",
        "valid_to",
        "created_by",
        "approved_by",
        "approved_at",
    ):
        if not hasattr(row, optional):
            setattr(row, optional, None)

    restored = _vehicle_document_to_entity(row)

    assert restored == original


def test_status_maps_to_enum_not_raw_string() -> None:
    class _Row:
        pass

    row = _Row()
    for key, value in _vehicle_document_to_row_values(_chunk()).items():
        setattr(row, key, value)
    for optional in (
        "source_document_id",
        "source_revision",
        "source_url",
        "embedding_model",
        "embedding_version",
        "valid_from",
        "valid_to",
        "created_by",
        "approved_by",
        "approved_at",
    ):
        if not hasattr(row, optional):
            setattr(row, optional, None)

    restored = _vehicle_document_to_entity(row)

    assert isinstance(restored.status, VehicleDocumentStatus)


def test_document_repositories_exposes_vehicle_documents() -> None:
    from dataclasses import fields

    from src.document.infrastructure.repositories import DocumentRepositories

    names = {f.name for f in fields(DocumentRepositories)}
    assert "vehicle_documents" in names


def test_document_transaction_protocol_exposes_vehicle_documents() -> None:
    """Port phai khai bao vehicle_documents, khong chi class cu the.

    DocumentRepositories (dataclass) da co field nay, nhung DocumentTransaction
    (Protocol — thu ma toan bo thiet ke unit-of-work ton tai de cung cap) truoc
    day khong khai bao, nen bat cu cai gi type theo Protocol se khong "thay"
    duoc vehicle_documents. Kiem tra truc tiep annotation cua Protocol.
    """
    from src.document.application.ports import DocumentTransaction

    assert "vehicle_documents" in DocumentTransaction.__annotations__
