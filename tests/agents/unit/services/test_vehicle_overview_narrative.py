"""Câu kể chuyện của bài review crawl về không được lọt vào câu tư vấn (lượt dev 2026-09-24)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agents.services.vehicle_overview import _SentencePool


@pytest.mark.parametrize(
    "sentence",
    [
        "Trước đây, khi còn sử dụng xe gầm thấp, đây là những tình huống khiến anh Tùng ái ngại.",
        "Gia đình mình đi xa rất thoải mái.",
        "Theo anh Minh, xe chạy êm.",
        "Tôi đã lái thử và thấy tay lái nhẹ.",
    ],
)
def test_cau_ke_chuyen_bi_loai(sentence: str) -> None:
    assert _SentencePool(SimpleNamespace(dimensions=None)).usable(sentence) is False


@pytest.mark.parametrize(
    "sentence",
    ["Xe có 7 chỗ ngồi rộng rãi cho gia đình.", "Cửa sổ trời toàn cảnh mang lại không gian thoáng."],
)
def test_cau_du_kien_ve_xe_van_duoc_dung(sentence: str) -> None:
    assert _SentencePool(SimpleNamespace(dimensions=None)).usable(sentence) is True
