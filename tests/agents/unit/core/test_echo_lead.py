"""Câu trả lời phải NHẮC LẠI ý khách, hoặc nói rõ vì sao từ chối (Sếp 2026-09-23).

Lõi trả lời bằng mẫu câu cố định. Khi mẫu câu không khớp đúng thứ khách vừa hỏi
("xe nào cốp rộng nhất" → "em chưa có mẫu nào khác hợp hơn"), khách không biết
bot đang trả lời câu nào và nghe như bot nói vớ vẩn.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, FilterCriteria, Recommendation, VehiclePitch
from src.agents.core import render
from src.agents.core.act import act
from src.agents.core.actions import TEMPLATE_CLARIFY, Recommend, Reply
from src.agents.core.state import CoreState, Stage
from src.agents.domain.moderation_blocklist import MODERATION_BLOCK_MESSAGE
from src.agents.domain.values import SlotName as N
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
RUN_ID = UUID("99999999-9999-9999-9999-999999999999")
HOI = "xe nào cốp rộng nhất"


# ---------------------------------------------------------------- bộ trích thuần


@pytest.mark.parametrize(
    "message",
    ["xe nào cốp rộng nhất", "thế còn pin thì sao ạ", "có bản nào màu trắng không"],
)
def test_trich_lai_y_khach(message: str) -> None:
    lead = render.echo_lead(message)
    assert message[:20] in lead
    assert lead.startswith("Dạ,")


@pytest.mark.parametrize("message", ["ok", "ừ", "", "   ", "vâng"])
def test_cau_qua_ngan_thi_khong_trich(message: str) -> None:
    """Trích lại "ok" chỉ làm câu nghe máy móc."""

    assert render.echo_lead(message) == ""


@pytest.mark.parametrize(
    "message",
    ["cho tôi xem lfp_battery", "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA", "cốp 260.00 lít là sao"],
)
def test_chu_khach_dinh_ma_may_thi_bo_cau_nhac(message: str) -> None:
    """Chữ khách CHƯA kiểm: dính mã máy thì bỏ câu nhắc, KHÔNG làm hỏng cả lượt."""

    assert render.echo_lead(message) == ""
    assert render.with_echo(message, "Phần trả lời.") == "Phần trả lời."


def test_cau_dai_bi_cat_nhung_van_doc_duoc() -> None:
    dai = "tôi muốn một chiếc xe vừa rộng vừa tiết kiệm điện để chở gia đình đi chơi xa cuối tuần"
    lead = render.echo_lead(dai)
    assert len(lead) < len(dai) + 40
    assert lead.endswith('của anh/chị ạ:')
    assert render.assert_clean(lead) == lead


# ---------------------------------------------------------------- trên đường thật


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="danh mục",
            pitches=(
                VehiclePitch(
                    vehicle_id=UUID(V1), rank=1, display_name="VinFast VF 3", pitch="",
                    starting_price_vnd=Decimal("278000000"),
                ),
                VehiclePitch(
                    vehicle_id=UUID(V2), rank=2, display_name="VinFast VF 2", pitch="",
                    starting_price_vnd=Decimal("188000000"),
                ),
            ),
        )


class _EmptyRetrieval:
    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        return []

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids: Any) -> list:
        return []


class _EmptyRecommendation:
    async def recommend(self, run_id: UUID, **_: Any) -> list[Recommendation]:
        return []


def _state() -> CoreState:
    return CoreState(
        session_id="s1", stage=Stage.RECOMMENDED, recommended_ids=(V1, V2),
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 400_000_000},
    )


@pytest.mark.asyncio
async def test_no_better_nhac_lai_y_khach() -> None:
    """Đo trên máy: "xe nào cốp rộng nhất" nhận "em chưa có mẫu nào khác hợp hơn"."""

    services = AgentServices(
        catalog_browse=_Catalog(), retrieval=_EmptyRetrieval(), recommendation=_EmptyRecommendation()
    )
    result = await act(
        Recommend(reason="revised", exclude_ids=(V1, V2), refine=HOI),
        _state(),
        services,
        run_id=RUN_ID,
        customer_id="c1",
        user_message=HOI,
    )
    assert HOI in result.text
    assert "chưa có mẫu nào khác hợp hơn" in result.text
    # Câu đuôi không được chỉ nói về tiền: khách vừa hỏi về CỐP.
    assert "bớt một tiêu chí" in result.text


@pytest.mark.asyncio
async def test_clarify_nhac_lai_y_khach() -> None:
    services = AgentServices(catalog_browse=_Catalog())
    result = await act(
        Reply(template=TEMPLATE_CLARIFY, args={"stage": Stage.RECOMMENDED.value, "user_message": HOI}),
        _state(),
        services,
        run_id=None,
        customer_id="c1",
        user_message=HOI,
    )
    assert HOI in result.text
    assert "em nghe anh/chị nói" in result.text


@pytest.mark.asyncio
async def test_clarify_khong_co_cau_khach_thi_van_ra_chu_cu() -> None:
    """Đường cũ (không truyền `user_message`) giữ nguyên hành vi, không vỡ."""

    services = AgentServices(catalog_browse=_Catalog())
    result = await act(
        Reply(template=TEMPLATE_CLARIFY, args={"stage": Stage.RECOMMENDED.value}),
        _state(),
        services,
        run_id=None,
        customer_id="c1",
        user_message=HOI,
    )
    assert result.text == render.render_reply(Reply(template=TEMPLATE_CLARIFY, args={"stage": "RECOMMENDED"}))


def test_cau_tu_choi_noi_ro_vi_sao_va_lam_duoc_gi() -> None:
    """Một câu "không hỗ trợ nội dung này" trơ nghe như bot né việc."""

    assert "ngoài phần em được phép trả lời" in MODERATION_BLOCK_MESSAGE
    assert "VinFast" in MODERATION_BLOCK_MESSAGE
    # Chỉ ra việc em LÀM ĐƯỢC, để khách biết đi tiếp bằng cách nào.
    for viec in ("giá lăn bánh", "tầm chạy", "lái thử"):
        assert viec in MODERATION_BLOCK_MESSAGE
    assert render.assert_clean(MODERATION_BLOCK_MESSAGE) == MODERATION_BLOCK_MESSAGE


def test_cau_nhac_khong_lam_vo_luot_khi_khach_go_ma_may() -> None:
    """Bất biến quan trọng nhất: câu nhắc trượt thì lượt vẫn có phần trả lời."""

    body = "Phần trả lời tất định."
    assert render.with_echo("cho tôi xem lfp_battery", body) == body
    assert render.with_echo("", body) == body
