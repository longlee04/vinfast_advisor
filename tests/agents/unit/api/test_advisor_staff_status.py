"""Màn TVV: phiên bot đã bàn giao phải hiện `WAITING_ADVISOR` (kiểm tra prod 2026-08-30)."""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.api.advisor_routes import _hitl_reasons, _staff_status


@dataclass
class _Item:
    status: str
    ownership: str = "AI"


def test_ban_giao_chua_ai_nhan_la_waiting_advisor() -> None:
    assert _staff_status(_Item("ACTIVE", "PENDING_HANDOFF")) == "WAITING_ADVISOR"
    assert _hitl_reasons(_Item("ACTIVE", "PENDING_HANDOFF"))


def test_ai_dang_cam_thi_giu_nguyen_status() -> None:
    assert _staff_status(_Item("ACTIVE")) == "ACTIVE"
    assert _hitl_reasons(_Item("ACTIVE")) == []
    assert _staff_status(_Item("COMPLETED", "PENDING_HANDOFF")) == "COMPLETED"


def test_review_detail_giu_lan_tan_da_luu_khi_khong_co_tin_hieu_xac_nhan() -> None:
    """Đọc thẳng dòng quyết định trong `operations/review.py`: overlay chỉ khi có evidence."""

    import inspect

    from src.agents.services.operations import review

    source = inspect.getsource(review)
    assert "builder.overlay(stored, evidence) if evidence else stored" in source


def test_so_moi_trong_bien_do_duoc_phep_ngoai_bien_do_thi_chan() -> None:
    """TVV phải viết được ưu đãi có số THẬT từ biên độ Admin (prod 2026-08-31 từng 422 mọi số)."""

    from src.agents.services.operations.review import numbers_added_illegally

    content = "Dạ, VinFast VF 5 đang có chương trình ưu đãi áp dụng ạ."
    allowed = {"10000000", "24"}
    assert numbers_added_illegally(content, "Giảm 10.000.000 đồng, trả góp 24 tháng ạ.", allowed) == []
    assert numbers_added_illegally(content, "Giảm 99.000.000 đồng ạ.", allowed) == ["99000000"]
