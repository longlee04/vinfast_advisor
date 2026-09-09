"""Bảng dịch mã kết thúc lượt ở biên công khai — chốt các cặp sống còn."""

from __future__ import annotations

from src.agents.contracts import PENDING_HANDOFF_REASON
from src.agents.services.output_guard import public_terminal_reason


def test_tvv_dang_cam_phien_thanh_advisor_active() -> None:
    """Silent khi TVV cầm phiên phải ra ADVISOR_ACTIVE — client mới biết đường im.

    Gộp về UNAVAILABLE là client tưởng bot lỗi, chèn câu fallback chen giữa
    cuộc chat với tư vấn viên (lỗi prod 2026-08-31).
    """
    assert public_terminal_reason(PENDING_HANDOFF_REASON) == "ADVISOR_ACTIVE"


def test_ma_noi_bo_la_van_gop_ve_unavailable() -> None:
    assert public_terminal_reason("GUARDRAIL_CONFIGURATION_ERROR") == "UNAVAILABLE"


def test_ma_cong_khai_giu_nguyen_va_none_giu_none() -> None:
    assert public_terminal_reason("ADVISOR_ACTIVE") == "ADVISOR_ACTIVE"
    assert public_terminal_reason(None) is None
