"""Integration tests for Gate A10 Brochure Ingestion & Admin Review (A10-1 to A10-5).

`session.execute()` là async nên session dùng `AsyncMock`, nhưng thứ nó TRẢ VỀ —
`Result` của SQLAlchemy — có API ĐỒNG BỘ (`scalar_one_or_none()`, `scalars()`,
`scalar()` đều không await). Mock chúng bằng `AsyncMock` khiến mỗi lần gọi trả
về một coroutine thay vì giá trị, và coroutine thì LUÔN truthy: nhánh "đã có bản
ghi" chạy với một object không có thuộc tính nào, nổ `AttributeError` cách chỗ
mock vài chục dòng. Vì vậy result và ORM row phải là `MagicMock`.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agents.adapters.feature_retriever import reverse_write_pending_flag
from src.auth.domain.authorization import Role
from src.document.application.brochure_ingestion import BrochureIngestionService
from src.document.presentation.admin_routes import ReviewActionRequest, review_feature_proposal
from src.document.presentation.dependencies import CurrentPrincipal
from src.products.infrastructure.models import VehicleFeatureFlagRow


@pytest.mark.asyncio
async def test_a10_4_and_a1_6_share_same_reverse_write_function_spy():
    """A10-4 & A1-6: Test both A10 brochure ingestion and A1-6 Hybrid RAG call the exact same reverse_write_pending_flag function."""
    mock_session = AsyncMock()
    # `session.add()` là API ĐỒNG BỘ; để nó là `AsyncMock` thì mỗi lần gọi
    # sinh một coroutine không ai await, và pytest báo `RuntimeWarning` ở một
    # dòng cách xa chỗ mock.
    mock_session.add = MagicMock()

    with patch("src.document.application.brochure_ingestion.reverse_write_pending_flag") as spy_write:
        spy_write.return_value = None

        service = BrochureIngestionService(mock_session)

        # Mock vehicle & features
        v_mock = MagicMock()
        v_mock.vehicle_id = str(uuid4())
        v_mock.vehicle_type = "CAR"

        f_mock = MagicMock()
        f_mock.feature_code = "PANORAMIC_ROOF"
        f_mock.name = "PANORAMIC_ROOF"
        f_mock.description = "VF8 Cua so troi toan canh"

        v_res = MagicMock()
        v_res.scalar_one_or_none.return_value = v_mock

        doc_res = MagicMock()
        doc_res.scalar_one_or_none.return_value = None

        rev_res = MagicMock()
        rev_res.scalar.return_value = "1"

        f_res = MagicMock()
        f_res.scalars.return_value.all.return_value = [f_mock]

        flag_res = MagicMock()
        flag_res.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [v_res, doc_res, rev_res, f_res, flag_res]

        # Chữ trong brochure phải khớp `f_mock.name` NGUYÊN VĂN, kể cả dấu:
        # `_propose_feature_flags` so bằng `name_kw in combined_text` — khớp
        # chuỗi con thuần, không bỏ dấu. Fixture cũ viết "Cua so troi" không dấu
        # nên không bao giờ khớp "Cửa sổ trời", và test không chạy tới lệnh gọi
        # `reverse_write_pending_flag` mà nó sinh ra để kiểm.
        pdf_bytes = "%PDF-1.4 BT (VF 8 co Cửa sổ trời toàn cảnh) Tj ET".encode()
        await service.ingest_brochure(v_mock.vehicle_id, pdf_bytes, filename="brochure.pdf")

        # Verify spy was called
        assert spy_write.called
        spy_write.assert_called_with(
            session=mock_session,
            vehicle_id=v_mock.vehicle_id,
            feature_code="PANORAMIC_ROOF",
            status="YES",
            confidence=0.85,
        )


@pytest.mark.asyncio
async def test_reverse_write_does_not_overwrite_approved_or_rejected_flags():
    """A10-4: Test reverse_write_pending_flag never overwrites APPROVED or REJECTED flags."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    # Existing APPROVED flag mock
    approved_flag = VehicleFeatureFlagRow(
        vehicle_id=str(uuid4()),
        feature_code="PANORAMIC_ROOF",
        status="YES",
        verification_status="APPROVED",
        confidence=1.0,
    )

    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = approved_flag
    mock_session.execute.return_value = res_mock

    # Attempt to reverse write a PENDING proposal for APPROVED flag
    await reverse_write_pending_flag(
        session=mock_session,
        vehicle_id=approved_flag.vehicle_id,
        feature_code="PANORAMIC_ROOF",
        status="NO",
        confidence=0.50,
    )

    # Assert status and verification_status remained APPROVED
    assert approved_flag.verification_status == "APPROVED"
    assert approved_flag.status == "YES"


@pytest.mark.asyncio
async def test_admin_review_approve_changes_flag_to_approved():
    """A10-5: Test Admin review approval updates verification_status from PENDING to APPROVED."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    v_id = str(uuid4())

    pending_flag = VehicleFeatureFlagRow(
        vehicle_id=v_id,
        feature_code="PANORAMIC_ROOF",
        status="YES",
        verification_status="PENDING",
        confidence=0.85,
    )

    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = pending_flag
    mock_session.execute.return_value = res_mock

    admin_principal = CurrentPrincipal(actor_id="admin_user", role=Role.ADMIN)
    req = ReviewActionRequest(vehicle_id=v_id, feature_code="PANORAMIC_ROOF", action="APPROVE")

    result = await review_feature_proposal(
        principal=admin_principal,
        request=req,
        session=mock_session,
    )

    assert result.verification_status == "APPROVED"
    assert pending_flag.verification_status == "APPROVED"
