"""Mỗi lượt đề xuất ghi ĐÚNG một dòng kết cục — mẫu số của mọi tỉ lệ về sau.

BÀI HỌC 2026-08-28, và là lỗi của chính bản đo trước: EM báo *"36/106 = 34% rơi
bản dựng tay"*. Sai mẫu số. `synthesis` **chỉ ghi log khi có vấn đề**, nên 106 là
tổng số dòng CẢNH BÁO, không phải tổng số lượt. Chia cho nó là chia cho một con
số không phải mẫu số.

Không có bộ đếm tổng thì mọi tỉ lệ đều là đoán — kể cả tỉ lệ dùng làm ngưỡng
phát hành. Dòng này là thứ làm cho câu "giảm 50%" có nghĩa.

Ghi ở mức `INFO`, một dòng một xe, mang đủ ba thứ để nhóm lại về sau: xe nào,
mấy claim được duyệt, và kết cục nào.
"""

from __future__ import annotations

import logging

import pytest

from src.agents.services.synthesis import SYNTHESIS_OUTCOME_EVENT, DefaultSynthesisService
from tests.agents.unit.services.test_synthesis import (  # noqa: F401
    RANGE_EVIDENCE_ID,
    RUN_ID,
    VEHICLE_ID,
    AllVehiclesFailLlm,
    FakeMultiVehicleSource,
    NameEchoLlm,
    _range_fact,
    _three_recommendations,
)


def _outcomes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if SYNTHESIS_OUTCOME_EVENT in record.getMessage()
    ]


@pytest.mark.asyncio
async def test_luot_viet_duoc_van_ghi_mot_dong(caplog: pytest.LogCaptureFixture) -> None:
    """Chỉ ghi lúc HỎNG thì không bao giờ biết mẫu số."""

    source = FakeMultiVehicleSource((_range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),))
    service = DefaultSynthesisService(llm=NameEchoLlm(), source=source)

    with caplog.at_level(logging.INFO, logger="src.agents.services.synthesis"):
        await service.synthesize(
            run_id=RUN_ID,
            recommendations=_three_recommendations()[:1],
            tco=None,
        )

    lines = _outcomes(caplog)
    assert len(lines) == 1
    assert "outcome=llm" in lines[0]
    assert str(VEHICLE_ID) in lines[0]


@pytest.mark.asyncio
async def test_luot_roi_ban_dung_tay_cung_ghi_cung_mot_dong(caplog: pytest.LogCaptureFixture) -> None:
    """Cùng một sự kiện, khác `outcome` — nhóm lại được bằng một lần đếm."""

    source = FakeMultiVehicleSource((_range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),))
    service = DefaultSynthesisService(llm=AllVehiclesFailLlm(), source=source)

    with caplog.at_level(logging.INFO, logger="src.agents.services.synthesis"):
        await service.synthesize(
            run_id=RUN_ID,
            recommendations=_three_recommendations()[:1],
            tco=None,
        )

    lines = _outcomes(caplog)
    assert len(lines) == 1
    assert "outcome=fallback" in lines[0]


@pytest.mark.asyncio
async def test_dong_ghi_mang_so_claim_da_duyet(caplog: pytest.LogCaptureFixture) -> None:
    """Bao nhiêu claim được duyệt là chỉ số Phase 0 phải theo dõi."""

    source = FakeMultiVehicleSource((_range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),))
    service = DefaultSynthesisService(llm=NameEchoLlm(), source=source)

    with caplog.at_level(logging.INFO, logger="src.agents.services.synthesis"):
        await service.synthesize(run_id=RUN_ID, recommendations=_three_recommendations()[:1], tco=None)

    assert "claims=" in _outcomes(caplog)[0]


@pytest.mark.asyncio
async def test_ba_xe_thi_ba_dong(caplog: pytest.LogCaptureFixture) -> None:
    """Mẫu số đếm theo XE, đúng đơn vị mà tỉ lệ rơi bản dựng tay nói tới."""

    source = FakeMultiVehicleSource(
        (
            _range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),
        )
    )
    service = DefaultSynthesisService(llm=NameEchoLlm(), source=source)

    with caplog.at_level(logging.INFO, logger="src.agents.services.synthesis"):
        pitches = await service.synthesize(run_id=RUN_ID, recommendations=_three_recommendations()[:1], tco=None)

    assert len(_outcomes(caplog)) == len(pitches)
