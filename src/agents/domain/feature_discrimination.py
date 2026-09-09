"""Chọn tính năng phân biệt cho lượt 2 (T7)."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID


def select_discriminating_features(
    *,
    candidate_features: Mapping[UUID, frozenset[str]],
    askable: frozenset[str],
    limit: int = 3,
    display_order: Mapping[str, int] | None = None,
) -> tuple[str, ...]:
    """Chọn feature chia tập ứng viên gần 50/50 nhất, nhiều nhất `limit` mã.

    Điểm mỗi feature: `min(n_có, n_tổng − n_có)`. Điểm 0 (mọi xe đều có hoặc
    không xe nào có) bị loại — hỏi cũng không lọc được gì. Chỉ xét feature trong
    `askable`. Trả rỗng thì bỏ hẳn lượt 2, đi thẳng tới đề xuất.
    """

    if not candidate_features:
        return ()
    vehicle_ids = list(candidate_features)
    total = len(vehicle_ids)
    order = display_order or {}
    scored: list[tuple[int, int, str]] = []  # (-điểm, display_order, code)
    seen: set[str] = set()
    for vehicle_id in vehicle_ids:
        for code in candidate_features[vehicle_id]:
            if code not in askable or code in seen:
                continue
            seen.add(code)
            count = sum(1 for vid in vehicle_ids if code in candidate_features[vid])
            score = min(count, total - count)
            if score <= 0:
                continue
            scored.append((-score, order.get(code, 0), code))
    scored.sort()
    return tuple(code for _, _, code in scored[:limit])
