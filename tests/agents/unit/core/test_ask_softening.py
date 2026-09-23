"""Câu hỏi hồ sơ: đổi cách nói, và hỏi LẠI thì phải thừa nhận trước.

Đo trên máy thật 2026-09-23: ba lượt liên tiếp nhận ĐÚNG MỘT chuỗi
("Để em gợi ý mẫu phù hợp nhất với anh/chị: ...") — khách tưởng bot hỏng. Hai
lớp sửa: biến thể tất định theo phiên (`prompts/question_variants`) và một câu
ghi nhận đứng trước mọi lần hỏi lại.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.core import render
from src.agents.core.act import act
from src.agents.core.actions import PENDING_PROFILE, Ask
from src.agents.core.state import CoreState, PendingKind, Stage
from src.agents.prompts.question_variants import PROFILE_VARIANTS, REASK_LEADS
from src.agents.services.registry import AgentServices

pytestmark = pytest.mark.asyncio


async def _ask_text(session_id: str, asked: int, **state_kw: Any) -> str:
    state = CoreState(
        session_id=session_id,
        stage=state_kw.pop("stage", Stage.COLLECTING),
        ask_counts={PENDING_PROFILE: asked} if asked else {},
        **state_kw,
    )
    result = await act(
        Ask(key=PENDING_PROFILE, kind=PendingKind.SLOT),
        state,
        AgentServices(),
        run_id=None,
        customer_id="c1",
        user_message="ờ thế à",
    )
    return result.text


async def test_hoi_lai_khong_lap_y_nguyen_cau_cu() -> None:
    """Cùng phiên, hỏi lần hai phải ra chữ KHÁC lần một."""

    lan_dau = await _ask_text("phien-1", asked=1)
    lan_hai = await _ask_text("phien-1", asked=2)
    assert lan_dau != lan_hai


async def test_hoi_lai_co_cau_ghi_nhan_dung_truoc() -> None:
    lan_dau = await _ask_text("phien-1", asked=1)
    lan_hai = await _ask_text("phien-1", asked=2)
    assert not any(lan_dau.startswith(lead) for lead in REASK_LEADS)
    assert any(lan_hai.startswith(lead) for lead in REASK_LEADS), lan_hai


async def test_hai_phien_khac_nhau_thi_mo_dau_khac_nhau() -> None:
    """Biến thể chống lặp GIỮA các hội thoại, không chỉ trong một hội thoại.

    (Lỗi cũ của lõi v1: cùng một câu hỏi lặp y nguyên 80 lần qua hàng chục phiên.)
    """

    texts = {await _ask_text(f"phien-{index}", asked=1) for index in range(12)}
    assert len(texts) >= 3


async def test_moi_bien_the_deu_la_cau_hoi_sach() -> None:
    """Mọi biến thể phải qua `assert_clean` và vẫn là một câu hỏi."""

    for variant in PROFILE_VARIANTS:
        assert render.assert_clean(variant) == variant
        assert variant.strip().endswith("?")
    for lead in REASK_LEADS:
        assert render.assert_clean(lead) == lead
        assert not any(char.isdigit() for char in lead)


async def test_cau_hoi_van_la_cau_ho_so_va_van_treo_pending() -> None:
    """Đổi cách nói KHÔNG được đổi việc: vẫn treo đúng `pending=profile`."""

    state = CoreState(session_id="phien-1", stage=Stage.COLLECTING, ask_counts={PENDING_PROFILE: 2})
    result = await act(
        Ask(key=PENDING_PROFILE, kind=PendingKind.SLOT),
        state,
        AgentServices(),
        run_id=None,
        customer_id="c1",
        user_message="ờ thế à",
    )
    pending = result.state_patch["pending"]
    assert pending.key == PENDING_PROFILE and pending.kind is PendingKind.SLOT
    assert any(variant in result.text for variant in PROFILE_VARIANTS)


async def test_cau_hoi_slot_khac_khong_bi_dong_vao() -> None:
    """Chỉ câu HỒ SƠ có biến thể; câu hỏi slot khác giữ nguyên chữ cũ."""

    state = CoreState(session_id="phien-1", stage=Stage.COLLECTING)
    result = await act(
        Ask(key="registration_province", kind=PendingKind.SLOT),
        state,
        AgentServices(),
        run_id=None,
        customer_id="c1",
        user_message="hà nội",
    )
    assert result.text == render.SLOT_QUESTIONS["registration_province"]
