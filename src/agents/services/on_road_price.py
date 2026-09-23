"""[A7-9] Use case giá lăn bánh: resolve biểu phí → gọi tool → dựng câu trả lời.

Đứng riêng khỏi `tco_estimation`: hai bên đọc chung bảng `tco_assumptions` nhưng
là hai câu hỏi khác nhau của khách, và gộp chung thì log/trace không phân biệt
được lượt nào tính giá lăn bánh, lượt nào ước tính chi phí sở hữu.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.pricing_intent import (
    PricingIntent,
    PricingRoute,
    classify_pricing_intent,
    detect_province,
    region_for_province_code,
    route_pricing_question,
)
from src.agents.prompts.pricing_reply import (
    MISSING_PROVINCE_QUESTION,
    MISSING_VARIANT_QUESTION,
    render_on_road_price,
)
from src.agents.services.pending_slot import pending_for_province
from src.agents.tools.on_road_price import (
    NATIONAL_REGION_CODE,
    OnRoadFeeAssumptions,
    vinfast_on_road_price_v1,
)

logger = logging.getLogger(__name__)


class OnRoadFeeSource(Protocol):
    """Đọc giá niêm yết và biểu phí đang hiệu lực của một xe."""

    async def load(self, *, vehicle_id: UUID, region_code: str, at: datetime) -> object | None: ...


class OnRoadPriceServiceImpl:
    """Trả câu giá lăn bánh, hoặc câu hỏi lại khi thiếu slot bắt buộc."""

    def __init__(self, source: OnRoadFeeSource) -> None:
        self._source = source

    async def answer(self, *, user_message: str, vehicle_id: UUID | None, vehicle_name: str) -> str | None:
        """Giữ lại cho chỗ gọi chỉ cần câu chữ."""

        text, _ = await self.answer_with_pending(
            user_message=user_message, vehicle_id=vehicle_id, vehicle_name=vehicle_name
        )
        return text

    async def answer_with_pending(
        self, *, user_message: str, canonical: CanonicalText, vehicle_id: UUID | None, vehicle_name: str
    ) -> tuple[str | None, PendingSlotRequest | None]:
        """`None` nghĩa là lượt này không phải câu hỏi giá lăn bánh.

        Trả CHUỖI HỎI LẠI khi thiếu tỉnh: đó là một câu trả lời hợp lệ, không
        phải lỗi — tính phí theo một tỉnh khách chưa nêu mới là lỗi.
        """

        if classify_pricing_intent(user_message, canonical) is not PricingIntent.ON_ROAD_PRICE_LOOKUP:
            return None, None
        province = detect_province(user_message, canonical)
        decision = route_pricing_question(
            intent=PricingIntent.ON_ROAD_PRICE_LOOKUP,
            vehicle_variant=vehicle_id,
            province=province,
        )
        if decision.route is PricingRoute.SLOT_FILLING:
            if "vehicle_variant" in decision.missing_slots:
                return MISSING_VARIANT_QUESTION, None
            # Ghi lại ĐANG CHỜ tỉnh. Thiếu bước này thì lượt sau khách đáp "hà
            # nội" và câu đó bị `classify_scope` gắn OUT_OF_SCOPE — đúng con bug
            # A7-10 sinh ra để sửa.
            question = MISSING_PROVINCE_QUESTION
            if vehicle_name:
                # Xưng tên xe: khách vừa xem VF 5 rồi nói "tính giá lăn bánh" cần
                # thấy hệ đã hiểu là xe nào, không phải một câu hỏi tỉnh trống.
                question = question.replace(
                    "tính giá lăn bánh chính xác", f"tính giá lăn bánh {vehicle_name} chính xác"
                )
            return question, pending_for_province(vehicle_id, vehicle_name, datetime.now(UTC))
        return await self._compute(vehicle_id, str(province), vehicle_name), None

    async def _compute(self, vehicle_id: UUID | None, province: str, name: str) -> str | None:
        """Đọc dữ liệu, tính, dựng câu. Thiếu dữ liệu thì trả `None` — nói không
        biết còn hơn dựng một tổng từ các khoản khuyết."""

        if vehicle_id is None:
            return None
        # Tra biểu phí theo MÃ KHU VỰC, không phải mã tỉnh: `tco_assumptions`
        # khoá theo `KHU_VUC_I`/`KHU_VUC_II`, truyền thẳng "HN" vào sẽ không khớp
        # dòng nào và câu trả lời biến mất im lặng.
        snapshot = await self._source.load(
            vehicle_id=vehicle_id,
            region_code=region_for_province_code(province),
            at=datetime.now(UTC),
        )
        fees = _fee_assumptions(snapshot)
        price = _listed_price(snapshot)
        if fees is None or price is None:
            logger.info("on-road price: thiếu dữ liệu giá hoặc biểu phí cho %s", vehicle_id)
            return None
        breakdown = vinfast_on_road_price_v1(listed_price_vnd=price, province=province, fees=fees)
        logger.info(
            "on-road price tính cho %s tại %s, biểu phí theo tỉnh=%s",
            vehicle_id,
            province,
            breakdown.province_specific,
        )
        return render_on_road_price(breakdown, name)


def _fee_assumptions(snapshot: object) -> OnRoadFeeAssumptions | None:
    """Rút biểu phí khỏi snapshot TCO. Thiếu khoản nào thì bỏ cả cụm.

    Không thay khoản khuyết bằng 0: một tổng thiếu phí biển số vẫn trông như một
    con số hoàn chỉnh, và khách sẽ mang nó đi so với báo giá của đại lý.
    """

    assumptions = getattr(snapshot, "assumptions", ()) or ()
    if not assumptions:
        return None
    row = assumptions[0]
    values = (
        row.registration_fee_percent,
        row.registration_fee_flat_vnd,
        row.plate_fee_vnd,
        row.mandatory_insurance_vnd_per_year,
    )
    if any(value is None for value in values):
        return None
    percent, flat, plate, insurance = values
    return OnRoadFeeAssumptions(
        region_code=getattr(row, "region_code", NATIONAL_REGION_CODE),
        registration_fee_percent=Decimal(str(percent)),
        registration_fee_flat_vnd=Decimal(str(flat)),
        plate_fee_vnd=Decimal(str(plate)),
        mandatory_insurance_vnd_per_year=Decimal(str(insurance)),
    )


#: Thứ tự ưu tiên loại giá, GIỮ NGUYÊN như `tools/tco._purchase_price`.
#: Hai câu trả lời cùng nói về một chiếc xe mà lấy hai mức giá khác nhau thì
#: khách sẽ thấy giá lăn bánh và chi phí sở hữu không khớp nhau.
_PRICE_PREFERENCE = ("BATTERY_INCLUDED", "BATTERY_INCLUDED_PRICE", "STARTING_PRICE")


def _listed_price(snapshot: object) -> Decimal | None:
    """Giá niêm yết đang hiệu lực; không có thì trả `None`."""

    prices = getattr(snapshot, "prices_vnd", None) or {}
    for price_type in _PRICE_PREFERENCE:
        amount = prices.get(price_type)
        if amount is not None:
            return Decimal(str(amount))
    return None


__all__ = ["OnRoadFeeSource", "OnRoadPriceServiceImpl"]
