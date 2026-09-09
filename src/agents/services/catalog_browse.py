"""[A4-7] Use case liệt kê danh mục theo loại xe — query + format, không hơn.

Không có bước tính toán nào ở đây, và đó là chủ ý: `CATALOG_BROWSE` chỉ đọc lại
những gì `vehicles`/`vehicle_prices` đã ghi. Vì vậy nó thuộc nhóm LOOKUP-tier
(dữ liệu công khai, không có yếu tố thương lượng) và KHÔNG qua HITL — cùng nguyên
tắc đã áp cho `ON_ROAD_PRICE_LOOKUP`, khác `TCO_ESTIMATE_LOOKUP` là thứ có nhiều
tầng giả định nên vẫn cần người duyệt.

Không gọi LLM: nhận diện loại xe là khớp từ khoá deterministic
(`domain/catalog_browse.py`), câu trả lời là template. Một lượt browse vì thế tốn
đúng một lần gọi LLM của bước trích slot, không thêm lần nào.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.agents.contracts import CatalogBrowseResult, VehiclePitch
from src.agents.domain.catalog_browse import (
    BROWSE_TYPE_ORDER,
    BrowseEntry,
    render_browse_answer,
    requested_vehicle_types,
)
from src.agents.domain.values import VehicleType
from src.agents.ports import CatalogReadPort


class CatalogBrowseServiceImpl:
    """Đọc danh mục theo loại rồi dựng câu trả lời đã format sẵn."""

    def __init__(self, catalog: CatalogReadPort) -> None:
        self._catalog = catalog

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult | None:
        """Câu trả lời danh mục, hoặc `None` khi không loại nào có xe đang bán.

        `None` chứ không phải một câu "hiện chưa có xe nào": danh mục rỗng gần
        như luôn là sự cố kết nối dữ liệu chứ không phải sự thật kinh doanh, và
        nói với khách rằng cửa hàng không còn xe nào là một câu sai đắt hơn
        nhiều so với việc để lượt rơi về nhánh hỏi lại.
        """

        try:
            default_vehicle_type = VehicleType(vehicle_type_hint) if vehicle_type_hint is not None else None
        except ValueError:
            default_vehicle_type = None
        vehicle_types = requested_vehicle_types(user_message, default_vehicle_type=default_vehicle_type)
        groups = {vehicle_type: await self._entries(vehicle_type) for vehicle_type in vehicle_types}
        answer = render_browse_answer(groups)
        if answer is None:
            return None
        entries = [
            entry
            for vehicle_type in BROWSE_TYPE_ORDER
            for entry in sorted(
                groups.get(vehicle_type, ()),
                key=lambda item: (
                    item.starting_price_vnd is None,
                    item.starting_price_vnd or 0,
                    item.display_name,
                ),
            )
        ]
        return CatalogBrowseResult(
            answer=answer,
            pitches=tuple(
                VehiclePitch(
                    vehicle_id=entry.vehicle_id,
                    rank=rank,
                    display_name=entry.display_name,
                    pitch=(
                        "Mẫu xe đang có trong danh mục VinFast. Anh/chị có thể chọn "
                        "mẫu này để em gửi thông số chi tiết hoặc so sánh thêm ạ."
                    ),
                    starting_price_vnd=(
                        format(entry.starting_price_vnd, "f") if entry.starting_price_vnd is not None else None
                    ),
                )
                for rank, entry in enumerate(entries, start=1)
            ),
        )

    async def _entries(self, vehicle_type: VehicleType) -> Sequence[BrowseEntry]:
        return await self._catalog.browse_catalog(vehicle_type)


__all__ = ["CatalogBrowseServiceImpl"]
