"""Unit tests for Gate A10 Brochure Ingestion Pipeline (A10-1 to A10-5)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.auth.domain.authorization import Role
from src.document.application.brochure_ingestion import BrochureIngestionService
from src.document.infrastructure.pdf_extractor import PDFTextExtractionError, extract_pdf_sections
from src.document.presentation.admin_routes import (
    _require_admin,
)
from src.document.presentation.dependencies import CurrentPrincipal


def test_pdf_extraction_scanned_pdf_raises_explicit_error():
    """A10-2: Test scanned PDF without text layer raises explicit PDFTextExtractionError."""
    # Bytes representing a scanned PDF with no BT...ET text stream or ASCII text
    scanned_bytes = b"%PDF-1.4 %FAKE_IMAGE_ONLY_STREAM \x00\x01\x02\x03\x04"
    with pytest.raises(PDFTextExtractionError, match="without text layer is not supported"):
        extract_pdf_sections(scanned_bytes, filename="scan_sample.pdf")


def test_pdf_extraction_preserves_equipment_table_block():
    """A10-2: Test equipment table block is preserved as a single unbroken section."""
    sample_pdf_bytes = (
        b"%PDF-1.4 BT (VinFast VF 8 Brochure) Tj ET BT (Bang trang bi va Thong so ky thuat) Tj ET "
        b"BT (Phien ban Eco va Plus 5 cho ngoi) Tj ET"
    )
    sections = extract_pdf_sections(sample_pdf_bytes, filename="vf8.pdf")
    assert len(sections) >= 1
    table_section = [s for s in sections if s[1] == "Bảng trang bị"]
    assert len(table_section) == 1
    assert "Bang trang bi" in table_section[0][2]


@pytest.mark.asyncio
async def test_brochure_ingestion_duplicate_pdf_returns_existing_document():
    """A10-1: Test ingesting duplicate PDF with same content_hash does not duplicate chunks."""
    mock_session = AsyncMock()

    # Existing vehicle mock
    v_mock = MagicMock()
    v_mock.vehicle_id = str(uuid4())
    v_mock.model_name = "VF 8"
    v_mock.vehicle_type = "CAR"

    # Existing document mock matching content_hash
    existing_doc = MagicMock()
    existing_doc.id = str(uuid4())

    v_res = MagicMock()
    v_res.scalar_one_or_none.return_value = v_mock

    doc_res = MagicMock()
    doc_res.scalar_one_or_none.return_value = existing_doc

    rev_res = MagicMock()
    rev_res.scalar.return_value = "1"

    mock_session.execute.side_effect = [v_res, doc_res, rev_res]

    pdf_bytes = b"%PDF-1.4 BT (VF8 Specs) Tj ET"
    service = BrochureIngestionService(mock_session)

    result = await service.ingest_brochure(v_mock.vehicle_id, pdf_bytes, filename="vf8.pdf")

    assert result.is_duplicate is True
    assert result.chunks_created == 0
    assert result.document_id == existing_doc.id


@pytest.mark.asyncio
async def test_brochure_ingestion_creates_draft_chunks_and_pending_proposals():
    """A10-3 & A10-4: Test new brochure PDF creates DRAFT chunks and PENDING feature proposals."""
    mock_session = AsyncMock()

    cand_v_id = str(uuid4())
    v_mock = MagicMock()
    v_mock.vehicle_id = cand_v_id
    v_mock.model_name = "VF 8"
    v_mock.vehicle_type = "CAR"

    v_res = MagicMock()
    v_res.scalar_one_or_none.return_value = v_mock

    doc_res = MagicMock()
    doc_res.scalar_one_or_none.return_value = None  # No duplicate

    max_rev_res = MagicMock()
    max_rev_res.scalar.return_value = None  # First revision

    # Active feature definitions mock
    f_row = MagicMock()
    f_row.feature_code = "PANORAMIC_ROOF"
    f_row.name = "PANORAMIC_ROOF"
    f_row.description = "Cửa sổ trời toàn cảnh"

    f_res = MagicMock()
    f_res.scalars.return_value.all.return_value = [f_row]

    # Existing feature flag mock (None so new PENDING flag created)
    flag_res = MagicMock()
    flag_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [v_res, doc_res, max_rev_res, f_res, flag_res]

    pdf_bytes = b"%PDF-1.4 BT (VinFast VF8 featuring PANORAMIC_ROOF) Tj ET"
    service = BrochureIngestionService(mock_session)

    result = await service.ingest_brochure(cand_v_id, pdf_bytes, filename="vf8_new.pdf")

    assert result.is_duplicate is False
    assert result.revision == "1"
    assert result.chunks_created >= 1
    assert result.feature_proposals_created >= 1


@pytest.mark.asyncio
async def test_admin_review_authorization_policy():
    """A10-5: Test CUSTOMER and ADVISOR roles are rejected with 403, ADMIN permitted."""
    cust_principal = CurrentPrincipal(actor_id="cust_1", role=Role.CUSTOMER)
    adv_principal = CurrentPrincipal(actor_id="adv_1", role=Role.ADVISOR)
    admin_principal = CurrentPrincipal(actor_id="admin_1", role=Role.ADMIN)

    with pytest.raises(HTTPException) as exc_info1:
        _require_admin(cust_principal)
    assert exc_info1.value.status_code == status.HTTP_403_FORBIDDEN

    with pytest.raises(HTTPException) as exc_info2:
        _require_admin(adv_principal)
    assert exc_info2.value.status_code == status.HTTP_403_FORBIDDEN

    assert _require_admin(admin_principal) == admin_principal
