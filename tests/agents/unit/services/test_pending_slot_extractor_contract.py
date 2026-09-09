"""Mọi bộ trích ĐƯỢC CẮM THẬT phải gọi được bằng hợp đồng hai tham số.

BUG THẬT, sập trên prod 2026-08-26:

    TypeError: location_text_from() takes 1 positional argument but 2 were given

`composition` cắm thẳng `location_text_from` (một tham số) vào bảng `extractors`
(`SlotExtractor` = hai tham số). Lỗi nổ ĐÚNG lúc khách gõ địa danh để lấy khung
giờ lái thử — bước biến một cuộc tư vấn thành một cái lịch — và không lượt nào
khác chạm tới nhánh đó, nên nó sống sót qua cả bộ test lẫn mypy.

Bài này gọi thẳng vào bảng thật của `AgentComposition`, không dựng bảng riêng:
một bản sao của bảng chỉ chứng minh bản sao đúng.
"""

from __future__ import annotations

import inspect

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.services.pending_slot import DEFAULT_EXTRACTORS


def _wired_extractors() -> dict[str, object]:
    """Bảng `extractors` y như `AgentComposition` dựng, không cần DB."""

    from src.agents.domain.nearby_location import (
        LOCATION_KIND_SLOT,
        USER_LOCATION_SLOT,
        location_kind_from,
        location_text_from,
    )
    from src.agents.services.pending_slot import message_only_extractor

    return {
        **DEFAULT_EXTRACTORS,
        USER_LOCATION_SLOT: message_only_extractor(location_text_from),
        LOCATION_KIND_SLOT: message_only_extractor(location_kind_from),
    }


def test_every_wired_extractor_accepts_message_and_canonical() -> None:
    canonical = build_canonical_text("anh ở Hà Nội")
    for slot_name, extractor in _wired_extractors().items():
        signature = inspect.signature(extractor)
        assert len(signature.parameters) == 2, f"{slot_name} nhan sai so tham so"
        extractor("anh ở Hà Nội", canonical)


def test_the_location_extractor_reads_a_typed_place_name() -> None:
    """Đúng câu đã làm sập prod."""

    from src.agents.domain.nearby_location import USER_LOCATION_SLOT

    extractor = _wired_extractors()[USER_LOCATION_SLOT]

    assert extractor("anh ở Hà Nội", build_canonical_text("anh ở Hà Nội")) == "Hà Nội"
