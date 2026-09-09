"""Thuần code xếp hạng ứng viên cho preview, không gọi LLM, không ghi DB.

`rank_by_popularity` chỉ ảnh hưởng thứ tự hiển thị của một danh sách chưa cá nhân
hoá — khác với scoring ở FULL pipeline, vốn sinh lý do khuyến nghị từ slot.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.agents.contracts import VehicleFacts


def rank_by_popularity(candidates: Sequence[VehicleFacts]) -> list[VehicleFacts]:
    """Sắp xếp ứng viên preview.

    - Ưu tiên các xe có giá niêm yết rõ ràng.
    - Đa dạng hoá các dòng xe (mỗi dòng lấy phiên bản tiêu biểu trước).
    - Sắp xếp từ phân khúc cao cấp đến dễ tiếp cận (VF 9 -> VF 8 -> VF 7 -> VF 6 -> VF 5 -> VF 3...)
      để khách hàng có cái nhìn bao quát toàn bộ dải sản phẩm VinFast.
    """
    with_price = [c for c in candidates if c.starting_price_vnd is not None]
    without_price = [c for c in candidates if c.starting_price_vnd is None]

    sorted_by_price_desc = sorted(with_price, key=lambda c: c.starting_price_vnd or 0, reverse=True)

    seen_base_models: set[str] = set()
    primary_picks: list[VehicleFacts] = []
    other_variants: list[VehicleFacts] = []

    for c in sorted_by_price_desc:
        words = c.display_name.split()
        base_name = " ".join(words[:3]) if len(words) >= 3 else c.display_name
        if base_name not in seen_base_models:
            seen_base_models.add(base_name)
            primary_picks.append(c)
        else:
            other_variants.append(c)

    return primary_picks + other_variants + without_price
