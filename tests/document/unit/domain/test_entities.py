from datetime import UTC, datetime

import pytest

from src.document.domain.entities import Document, DocumentMetadata
from src.document.domain.errors import (
    ArchivedDocumentError,
    InvalidDocumentIdError,
    InvalidTitleError,
    UnsupportedStatusTransitionError,
)
from src.document.domain.values import ApprovalStatus, DocumentId, ProcessingStatus


def test_document_defaults_and_archive_are_idempotent() -> None:
    document = Document.create(DocumentMetadata(title="Policy", content_hash="abc"), created_by="admin")

    assert document.approval_status is ApprovalStatus.DRAFT
    assert document.processing_status is ProcessingStatus.NOT_STARTED
    archived = document.archive("admin", datetime.now(UTC))

    assert archived.archived_at is not None
    assert archived.archive("admin", datetime.now(UTC)) == archived


def test_document_rejects_invalid_id_and_empty_title() -> None:
    with pytest.raises(InvalidDocumentIdError):
        DocumentId("not-a-uuid")
    with pytest.raises(InvalidTitleError):
        Document.create(DocumentMetadata(title="   ", content_hash="abc"), created_by="admin")


def test_document_rejects_unsupported_processing_transition() -> None:
    document = Document.create(DocumentMetadata(title="Policy", content_hash="abc"), created_by="admin")

    with pytest.raises(UnsupportedStatusTransitionError):
        document.transition_processing(ProcessingStatus.COMPLETED)


def test_archived_document_rejects_mutation() -> None:
    document = Document.create(DocumentMetadata(title="Policy", content_hash="abc"), created_by="admin")
    archived = document.archive("admin", datetime.now(UTC))

    with pytest.raises(ArchivedDocumentError):
        archived.update_title("New title")


def test_duplicate_content_hash_is_not_a_domain_error() -> None:
    first = Document.create(DocumentMetadata(title="One", content_hash="same"), created_by="admin")
    second = Document.create(DocumentMetadata(title="Two", content_hash="same"), created_by="admin")

    assert first.content_hash == second.content_hash
    assert first.id != second.id
